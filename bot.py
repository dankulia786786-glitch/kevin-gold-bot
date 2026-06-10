import os
import asyncio
import aiohttp
from flask import Flask, request, jsonify
import threading
import json

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
PM_BOT    = os.environ.get("PM_BOT", "https://t.me/Test_indicator01_bot")
OWNER_ID  = os.environ.get("OWNER_ID", "8842842151")

active_trade = None

async def send_telegram(message, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)

async def send_to_owner(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={
            "chat_id": OWNER_ID,
            "text": message,
            "parse_mode": "HTML"
        })

async def send_to_user(user_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={
            "chat_id": user_id,
            "text": message,
            "parse_mode": "HTML"
        })

def join_button():
    return {
        "inline_keyboard": [[
            {"text": "👉 Join PM Now For Free", "url": PM_BOT}
        ]]
    }

async def get_gold_price():
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
    global active_trade
    direction = trade["direction"]
    tp1 = float(trade["tp1"])
    tp2 = float(trade["tp2"])
    tp3 = float(trade["tp3"])
    sl  = float(trade["sl"])
    tp1_hit = tp2_hit = tp3_hit = sl_hit = False

    for _ in range(1440):
        await asyncio.sleep(60)
        price = await get_gold_price()
        if price is None:
            continue

        if direction == "BUY":
            if not tp1_hit and price >= tp1:
                tp1_hit = True
                await send_telegram(
                    "GOLD SMASHED TP1 ✅✅✅\n\n"
                    "☑️ Close your positions now and secure your profits\n\n"
                    "Or\n\n"
                    "☑️ Move your SL to Break Even and let the trade run risk free",
                    reply_markup=join_button()
                )
            if tp1_hit and not tp2_hit and price >= tp2:
                tp2_hit = True
                await send_telegram(
                    "GOLD SMASHED TP2 ✅✅✅✅\n\n"
                    "☑️ Close remaining positions and secure your profits\n\n"
                    "Or\n\n"
                    "☑️ Let the remaining trade run risk free to TP3",
                    reply_markup=join_button()
                )
            if tp2_hit and not tp3_hit and price >= tp3:
                tp3_hit = True
                await send_telegram(
                    "🏆 GOLD SMASHED TP3 ✅✅✅✅✅\n\n"
                    "☑️ ALL TARGETS HIT!\n\n"
                    "💰 Full profits secured.\n\n"
                    "👏 Well done team!",
                    reply_markup=join_button()
                )
                active_trade = None
                break
            if not sl_hit and price <= sl:
                sl_hit = True
                await send_telegram(
                    "🛑 GOLD SL HIT\n\n"
                    "❌ Stop Loss has been reached\n\n"
                    "☑️ Close your positions and wait for next signal"
                )
                active_trade = None
                break

        elif direction == "SELL":
            if not tp1_hit and price <= tp1:
                tp1_hit = True
                await send_telegram(
                    "GOLD SMASHED TP1 ✅✅✅\n\n"
                    "☑️ Close your positions now and secure your profits\n\n"
                    "Or\n\n"
                    "☑️ Move your SL to Break Even and let the trade run risk free",
                    reply_markup=join_button()
                )
            if tp1_hit and not tp2_hit and price <= tp2:
                tp2_hit = True
                await send_telegram(
                    "GOLD SMASHED TP2 ✅✅✅✅\n\n"
                    "☑️ Close remaining positions and secure your profits\n\n"
                    "Or\n\n"
                    "☑️ Let the remaining trade run risk free to TP3",
                    reply_markup=join_button()
                )
            if tp2_hit and not tp3_hit and price <= tp3:
                tp3_hit = True
                await send_telegram(
                    "🏆 GOLD SMASHED TP3 ✅✅✅✅✅\n\n"
                    "☑️ ALL TARGETS HIT!\n\n"
                    "💰 Full profits secured.\n\n"
                    "👏 Well done team!",
                    reply_markup=join_button()
                )
                active_trade = None
                break
            if not sl_hit and price >= sl:
                sl_hit = True
                await send_telegram(
                    "🛑 GOLD SL HIT\n\n"
                    "❌ Stop Loss has been reached\n\n"
                    "☑️ Close your positions and wait for next signal"
                )
                active_trade = None
                break

    active_trade = None

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.close()

# ─── RECEIVE MESSAGES FROM USERS ─────────────────────────────
@app.route("/telegram_update", methods=["POST"])
def telegram_update():
    data = request.get_json()
    if not data:
        return jsonify({"ok": True})
    try:
        message = data.get("message", {})
        if not message:
            return jsonify({"ok": True})
        user     = message.get("from", {})
        text     = message.get("text", "")
        username = user.get("username", "No username")
        name     = user.get("first_name", "Unknown")
        user_id  = user.get("id", "")

        # Forward to Kevin personally
        forward_msg = (
            f"📩 <b>New PM Request!</b>\n\n"
            f"👤 Name: {name}\n"
            f"🔗 Username: @{username}\n"
            f"💬 Message: {text}\n\n"
            f"<a href='tg://user?id={user_id}'>👉 Click to reply to them</a>"
        )
        threading.Thread(target=run_async, args=(send_to_owner(forward_msg),)).start()

        # Auto reply to user
        auto_reply = (
            f"Hi {name}! 👋\n\n"
            f"Thanks for reaching out!\n\n"
            f"Kevin will message you shortly with details on how to join the PM group! 🏆"
        )
        threading.Thread(target=run_async, args=(send_to_user(user_id, auto_reply),)).start()

    except Exception as e:
        print(f"Error: {e}")
    return jsonify({"ok": True})

# ─── SIGNAL WEBHOOK ──────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    global active_trade
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    signal = data.get("signal", "").upper()
    price  = float(data.get("price", 0))

    if active_trade is not None:
        return jsonify({"status": "ignored", "reason": "trade already active"}), 200

    if signal == "BUY":
        emoji      = "🟢"
        tp1        = round(price + 4,  2)
        tp2        = round(price + 6,  2)
        tp3        = round(price + 10, 2)
        sl         = round(price - 8,  2)
        entry_low  = round(price - 2,  2)
        entry_high = round(price + 2,  2)
    elif signal == "SELL":
        emoji      = "🔴"
        tp1        = round(price - 4,  2)
        tp2        = round(price - 6,  2)
        tp3        = round(price - 10, 2)
        sl         = round(price + 8,  2)
        entry_low  = round(price - 2,  2)
        entry_high = round(price + 2,  2)
    else:
        return jsonify({"error": "Invalid signal"}), 400

    active_trade = signal

    message = (
        f"{emoji} <b>{signal}</b>\n"
        f"XAU/USD | GOLD\n\n"
        f"ENTRY : {entry_low} – {entry_high}\n\n"
        f"✅ TP1 {tp1}\n"
        f"✅ TP2 {tp2}\n"
        f"✅ TP3 {tp3}\n"
        f"🛑 SL {sl}\n\n"
        f"<i>(Use Appropriate Lot Sizes)</i>"
    )

    threading.Thread(target=run_async, args=(send_telegram(message),)).start()

    trade = {
        "direction": signal,
        "entry": price,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl
    }
    threading.Thread(target=run_async, args=(monitor_trade(trade),)).start()

    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def home():
    return "Kevin Gold Signals Bot is running! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
