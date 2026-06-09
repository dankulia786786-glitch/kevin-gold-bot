import os
import asyncio
import aiohttp
from flask import Flask, request, jsonify
import threading
import json

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# Store active trades being monitored
active_trades = []

async def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })

async def get_gold_price():
    """Get current XAUUSD price from a free API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d",
                headers={"User-Agent": "Mozilla/5.0"}
            ) as resp:
                data = await resp.json()
                price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
                return float(price)
    except:
        return None

async def monitor_trade(trade):
    """Monitor a trade and send TP/SL alerts"""
    direction = trade["direction"]
    entry = trade["entry"]
    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    tp3 = trade["tp3"]
    sl = trade["sl"]

    tp1_hit = False
    tp2_hit = False
    tp3_hit = False
    sl_hit = False

    # Monitor for up to 24 hours
    for _ in range(1440):
        await asyncio.sleep(60)  # Check every minute

        price = await get_gold_price()
        if price is None:
            continue

        if direction == "BUY":
            if not tp1_hit and price >= tp1:
                tp1_hit = True
                await send_telegram(
                    f"GOLD SMASHED TP1 ✅✅✅\n\n"
                    f"☑️ Close your positions now and secure your profits\n\n"
                    f"Or\n\n"
                    f"☑️ Move your SL to Break Even and let the trade run risk free"
                )

            if tp1_hit and not tp2_hit and price >= tp2:
                tp2_hit = True
                await send_telegram(
                    f"GOLD SMASHED TP2 ✅✅✅✅\n\n"
                    f"☑️ Close remaining positions and secure your profits\n\n"
                    f"Or\n\n"
                    f"☑️ Let the remaining trade run risk free to TP3"
                )

            if tp2_hit and not tp3_hit and price >= tp3:
                tp3_hit = True
                await send_telegram(
                    f"🏆 GOLD SMASHED TP3 ✅✅✅✅✅\n\n"
                    f"☑️ Full trade complete! Close all positions\n\n"
                    f"💰 Excellent trade! Well done team!"
                )
                break

            if not sl_hit and price <= sl:
                sl_hit = True
                await send_telegram(
                    f"🛑 GOLD SL HIT\n\n"
                    f"❌ Stop Loss has been reached\n\n"
                    f"☑️ Close your positions and wait for next signal"
                )
                break

        elif direction == "SELL":
            if not tp1_hit and price <= tp1:
                tp1_hit = True
                await send_telegram(
                    f"GOLD SMASHED TP1 ✅✅✅\n\n"
                    f"☑️ Close your positions now and secure your profits\n\n"
                    f"Or\n\n"
                    f"☑️ Move your SL to Break Even and let the trade run risk free"
                )

            if tp1_hit and not tp2_hit and price <= tp2:
                tp2_hit = True
                await send_telegram(
                    f"GOLD SMASHED TP2 ✅✅✅✅\n\n"
                    f"☑️ Close remaining positions and secure your profits\n\n"
                    f"Or\n\n"
                    f"☑️ Let the remaining trade run risk free to TP3"
                )

            if tp2_hit and not tp3_hit and price <= tp3:
                tp3_hit = True
                await send_telegram(
                    f"🏆 GOLD SMASHED TP3 ✅✅✅✅✅\n\n"
                    f"☑️ Full trade complete! Close all positions\n\n"
                    f"💰 Excellent trade! Well done team!"
                )
                break

            if not sl_hit and price >= sl:
                sl_hit = True
                await send_telegram(
                    f"🛑 GOLD SL HIT\n\n"
                    f"❌ Stop Loss has been reached\n\n"
                    f"☑️ Close your positions and wait for next signal"
                )
                break

        if tp3_hit or sl_hit:
            break

    # Remove trade from active list
    if trade in active_trades:
        active_trades.remove(trade)

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.close()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data"}), 400

    signal = data.get("signal", "").upper()
    price = float(data.get("price", 0))

    if signal == "BUY":
        tp1 = round(price + 20, 2)
        tp2 = round(price + 40, 2)
        tp3 = round(price + 100, 2)
        sl  = round(price - 10, 2)
        emoji = "🟢"
        direction = "BUY"
    elif signal == "SELL":
        tp1 = round(price - 20, 2)
        tp2 = round(price - 40, 2)
        tp3 = round(price - 100, 2)
        sl  = round(price + 10, 2)
        emoji = "🔴"
        direction = "SELL"
    else:
        return jsonify({"error": "Invalid signal"}), 400

    # Format entry range (entry ± 5)
    entry_low  = round(price - 5, 2)
    entry_high = round(price + 5, 2)

    message = (
        f"{emoji} {signal}\n"
        f"XAU/USD | GOLD\n\n"
        f"ENTRY : {entry_low} - {entry_high}\n\n"
        f"✅ TP1 {tp1}\n"
        f"✅ TP2 {tp2}\n"
        f"✅ TP3 {tp3}\n"
        f"🛑 SL {sl}\n\n"
        f"(Use Appropriate Lot Sizes)"
    )

    # Send the signal message
    threading.Thread(
        target=run_async,
        args=(send_telegram(message),)
    ).start()

    # Start monitoring for TP/SL hits
    trade = {
        "direction": direction,
        "entry": price,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl
    }
    active_trades.append(trade)
    threading.Thread(
        target=run_async,
        args=(monitor_trade(trade),)
    ).start()

    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def home():
    return "Kevin Gold Signals Bot is running! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
