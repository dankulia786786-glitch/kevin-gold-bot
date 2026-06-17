//+------------------------------------------------------------------+
//|  KevinGoldAutoTrader.mq5                                         |
//|  v2.0 — EA handles ALL close notifications                      |
//+------------------------------------------------------------------+
#property copyright "Kevin Burns & Team"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>

//--- Inputs
input double InpLotSize      = 0.71;
input bool   InpAutoTrading  = true;
input int    InpMagicNumber  = 20250616;
input int    InpPollSeconds  = 5;
input string InpWebhookHost  = "kevin-gold-bot-production.up.railway.app";
input string InpSignalPath   = "/mt5_signal";
input string InpClosePath    = "/mt5_close";

CTrade   trade;
datetime lastPollTime  = 0;
string   lastSignalId  = "";
string   beAppliedFor  = "";

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFilling(ORDER_FILLING_FOK);
   Print("✅ KevinGoldAutoTrader v2.00 started. Lot=", InpLotSize);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(!InpAutoTrading) return;
   if((TimeCurrent() - lastPollTime) < InpPollSeconds) return;
   lastPollTime = TimeCurrent();

   // Poll for new entry signals
   string signal = FetchSignal();
   if(signal != "" && signal != "none")
   {
      string signalId = JsonGetString(signal, "id");
      if(signalId != lastSignalId && signalId != "")
      {
         lastSignalId = signalId;
         beAppliedFor = "";

         string pair      = JsonGetString(signal, "pair");
         string direction = JsonGetString(signal, "direction");
         double slPrice   = JsonGetDouble(signal, "sl");
         double tp1       = JsonGetDouble(signal, "tp1");
         double tp2       = JsonGetDouble(signal, "tp2");
         double tp3       = JsonGetDouble(signal, "tp3");
         bool   isBuy     = (direction == "BUY");
         string symbol    = (pair == "XAUUSD") ? "XAUUSD" : "BTCUSD";

         if(!SymbolSelect(symbol, true)) { Print("❌ Symbol not found: ", symbol); return; }

         ENUM_ORDER_TYPE orderType = isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

         Print("📡 Signal: ", direction, " ", pair,
               " SL=", slPrice, " TP1=", tp1, " TP2=", tp2, " TP3=", tp3);

         if(pair == "XAUUSD")
         {
            OpenTrade(symbol, orderType, InpLotSize, slPrice, tp1, "GOLD_TP1_" + signalId);
            OpenTrade(symbol, orderType, InpLotSize, slPrice, tp2, "GOLD_TP2_" + signalId);
            OpenTrade(symbol, orderType, InpLotSize, slPrice, tp3, "GOLD_TP3_" + signalId);
         }
         else
         {
            OpenTrade(symbol, orderType, InpLotSize, slPrice, tp1, "BTC_TP1_" + signalId);
         }
      }
   }

   // Background BE monitor
   CheckAndApplyBreakEven();
}

//+------------------------------------------------------------------+
void CheckAndApplyBreakEven()
{
   if(lastSignalId == "") return;
   if(beAppliedFor == lastSignalId) return;

   bool   tp1Exists     = false;
   bool   tp2or3Exists  = false;
   double entryPrice    = 0;
   ulong  tp2ticket     = 0, tp3ticket = 0;

   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      string comment = PositionGetString(POSITION_COMMENT);
      if(StringFind(comment, lastSignalId) < 0) continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);

      if(StringFind(comment, "_TP1_") >= 0)
      {
         tp1Exists  = true;
         entryPrice = openPrice;
      }
      else if(StringFind(comment, "_TP2_") >= 0)
      {
         tp2or3Exists = true;
         tp2ticket    = ticket;
         if(entryPrice == 0) entryPrice = openPrice;
      }
      else if(StringFind(comment, "_TP3_") >= 0)
      {
         tp2or3Exists = true;
         tp3ticket    = ticket;
         if(entryPrice == 0) entryPrice = openPrice;
      }
   }

   if(!tp1Exists && tp2or3Exists && entryPrice > 0)
   {
      Print("☑️ TP1 gone — applying BE at ", entryPrice);
      ulong tickets[2];
      tickets[0] = tp2ticket;
      tickets[1] = tp3ticket;

      bool anyMoved = false;
      for(int i = 0; i < 2; i++)
      {
         if(tickets[i] == 0) continue;
         if(!PositionSelectByTicket(tickets[i])) continue;

         double currentSL = PositionGetDouble(POSITION_SL);
         double currentTP = PositionGetDouble(POSITION_TP);
         ENUM_POSITION_TYPE posType =
            (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

         bool shouldMove =
            (posType == POSITION_TYPE_BUY  && entryPrice > currentSL) ||
            (posType == POSITION_TYPE_SELL && entryPrice < currentSL);

         if(shouldMove && trade.PositionModify(tickets[i], entryPrice, currentTP))
         {
            Print("✅ BE set for ticket ", tickets[i]);
            anyMoved = true;
         }
      }
      if(anyMoved) beAppliedFor = lastSignalId;
   }
}

//+------------------------------------------------------------------+
void OpenTrade(string symbol, ENUM_ORDER_TYPE type, double lots,
               double sl, double tp, string comment)
{
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);

   bool result = (type == ORDER_TYPE_BUY)
                 ? trade.Buy(lots, symbol, 0, sl, tp, comment)
                 : trade.Sell(lots, symbol, 0, sl, tp, comment);

   if(result) Print("✅ Opened: ", comment, " SL=", sl, " TP=", tp);
   else        Print("❌ Failed: ", comment, " Error=", GetLastError());
}

//+------------------------------------------------------------------+
//| ALL close detection — TP1/TP2/TP3/SL/BE                         |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

   ulong dealTicket = trans.deal;
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagicNumber) return;

   ENUM_DEAL_ENTRY dealEntry =
      (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(dealEntry != DEAL_ENTRY_OUT) return;

   string comment    = HistoryDealGetString(dealTicket, DEAL_COMMENT);
   double dealProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
   double closePrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   string symbol     = HistoryDealGetString(dealTicket, DEAL_SYMBOL);
   double lots       = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   string pair       = (symbol == "XAUUSD") ? "XAUUSD" : "BTCUSD";

   ENUM_DEAL_REASON dealReason =
      (ENUM_DEAL_REASON)HistoryDealGetInteger(dealTicket, DEAL_REASON);

   Print("📤 Close detected: ", pair, " reason=", dealReason,
         " profit=", dealProfit, " comment=", comment);

   // Determine close type
   string closeType = "";

   if(dealReason == DEAL_REASON_SL)
   {
      closeType = "SL";
   }
   else if(dealReason == DEAL_REASON_TP || dealProfit > 0)
   {
      // Determine which TP by comment
      if(StringFind(comment, "_TP1_") >= 0)       closeType = "TP1";
      else if(StringFind(comment, "_TP2_") >= 0)  closeType = "TP2";
      else if(StringFind(comment, "_TP3_") >= 0)  closeType = "TP3";
      else if(StringFind(comment, "BTC_TP1") >= 0) closeType = "TP1";
      else
      {
         // Fallback: use profit size for Gold
         if(dealProfit > 60.0)      closeType = "TP3";
         else if(dealProfit > 25.0) closeType = "TP2";
         else                       closeType = "TP1";
      }
   }
   else
   {
      // Zero or negative profit, not SL reason = break even close — SILENT
      Print("☑️ Break even close detected — silent, no Telegram message");
      return;
   }

   if(closeType == "") return;

   Print("📨 Reporting to Railway: ", closeType, " for ", pair);
   ReportClose(pair, closeType, closePrice, dealProfit, lots, comment);
}

//+------------------------------------------------------------------+
void ReportClose(string pair, string closeType, double price,
                 double profit, double lots, string comment)
{
   string url = "https://" + InpWebhookHost + InpClosePath;

   string body = "{";
   body += "\"pair\":\"" + pair + "\",";
   body += "\"close_type\":\"" + closeType + "\",";
   body += "\"price\":" + DoubleToString(price, 2) + ",";
   body += "\"profit\":" + DoubleToString(profit, 2) + ",";
   body += "\"lots\":" + DoubleToString(lots, 2) + ",";
   body += "\"comment\":\"" + comment + "\"";
   body += "}";

   uchar postData[];
   StringToCharArray(body, postData, 0, StringLen(body));
   string headers = "Content-Type: application/json\r\n";
   uchar  response[];
   string responseHeaders;

   int res = WebRequest("POST", url, headers, 5000,
                        postData, response, responseHeaders);
   if(res == 200)
      Print("✅ Reported to Railway: ", closeType);
   else
      Print("⚠️ Failed. HTTP=", res, " Error=", GetLastError());
}

//+------------------------------------------------------------------+
string FetchSignal()
{
   string url = "https://" + InpWebhookHost + InpSignalPath;
   string headers = "Content-Type: application/json\r\n";
   char post[]; char response[]; string responseHeaders;
   int res = WebRequest("GET", url, headers, 5000,
                        post, response, responseHeaders);
   if(res != 200) return "";
   return CharArrayToString(response);
}

string JsonGetString(string json, string key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double JsonGetDouble(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0.0;
   start += StringLen(search);
   int end = start;
   while(end < StringLen(json))
   {
      ushort c = StringGetCharacter(json, end);
      if(c == ',' || c == '}' || c == ' ') break;
      end++;
   }
   return StringToDouble(StringSubstr(json, start, end - start));
}

void OnDeinit(const int reason)
{
   Print("KevinGoldAutoTrader v2.00 stopped. Reason=", reason);
}
