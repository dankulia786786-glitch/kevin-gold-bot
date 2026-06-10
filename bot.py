import os
import asyncio
import aiohttp
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import json

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
PM_BOT    = os.environ.get("PM_BOT", "https://t.me/Test_indicator01_bot")
OWNER_ID  = os.environ.get("OWNER_ID", "8842842151")

active_trades = {}

PAIR_CONFIG = {
    "XAUUSD": {"name": "XAU/USD | GOLD",     "entry_range": 2,   "tp1": 4,   "tp2": 6,   "tp3": 10,  "sl": 8},
    "BTCUSD": {"name": "BTC/USD | BITCOIN",   "entry_range": 300, "tp1": 100, "tp2": 150, "tp3": 500, "sl": 1000},
    "US30":   {"name": "US30 | DOW JONES",    "entry_range": 20,  "tp1": 30,  "tp2": 50,  "tp3": 100, "sl": 80},
    "USOIL":  {"name": "OIL | WTI CRUDE",     "entry_range": 0.5, "tp1": 0.5, "tp2": 1.0, "tp3": 2.0, "sl": 1.5},
}
DEFAULT_CONFIG = {"name": "SIGNAL", "entry_range": 2, "tp1": 4, "tp2": 6, "tp3": 10, "sl": 8}

async def send_telegram(message, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)

async def send_to_owner(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={"chat_id": OWNER_ID, "text": message, "parse_mode": "HTML"})

async def send_to_user(user_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={"chat_id": user_id, "text": message, "parse_mode": "HTML"})

def join_button():
    return {"inline_keyboard": [[{"text": "👉 JOIN PM NOW FOR FREE! 👈", "url": PM_BOT}]]}

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.close()

@app.route("/telegram_update", methods=["POST"])
def telegram_update():
    data = request.get_json()
    if not data:
        return jsonify({"ok": True})
    try:
        message  = data.get("message", {})
        if not message:
            return jsonify({"ok": True})
        user     = message.get("from", {})
        text     = message.get("text", "")
        username = user.get("username", "No username")
        name     = user.get("first_name", "Unknown")
        user_id  = user.get("id", "")
        forward_msg = (
            f"📩 <b>New PM Request!</b>\n\n"
            f"👤 Name: {name}\n"
            f"🔗 Username: @{username}\n"
            f"💬 Message: {text}\n\n"
            f"<a href='tg://user?id={user_id}'>👉 Click to reply to them</a>"
        )
        threading.Thread(target=run_async, args=(send_to_owner(forward_msg),)).start()
        auto_reply = (
            f"Hi {name}! 👋\n\n"
            f"Thanks for reaching out!\n\n"
            f"Kevin will message you shortly! 🏆"
        )
        threading.Thread(target=run_async, args=(send_to_user(user_id, auto_reply),)).start()
    except Exception as e:
        print(f"Error: {e}")
    return jsonify({"ok": True})

@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    global active_trades
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    pair   = data.get("pair", "XAUUSD").upper()
    price  = float(data.get("price", 0))
    config = PAIR_CONFIG.get(pair, DEFAULT_CONFIG)
    er     = config["entry_range"]
    event  = data.get("event", "").upper()

    # ── TP1 ──────────────────────────────────────────────────
    if event == "TP1":
        threading.Thread(target=run_async, args=(send_telegram(
            "<b>🏅 GOLD SMASHED TP1 ✅✅✅</b>\n\n"
            "☑️ Close your positions now and secure your profits\n\n"
            "Or\n\n"
            "☑️ Move your SL to Break Even and let the trade run risk free",
            reply_markup=join_button()
        ),)).start()
        return jsonify({"status": "tp1_sent"}), 200

    # ── TP2 ──────────────────────────────────────────────────
    if event == "TP2":
        threading.Thread(target=run_async, args=(send_telegram(
            "<b>🏅 GOLD SMASHED TP2 ✅✅✅✅</b>\n\n"
            "☑️ Close remaining positions and secure your profits\n\n"
            "Or\n\n"
            "☑️ Let the remaining trade run risk free to TP3",
            reply_markup=join_button()
        ),)).start()
        return jsonify({"status": "tp2_sent"}), 200

    # ── TP3 ──────────────────────────────────────────────────
    if event == "TP3":
        threading.Thread(target=run_async, args=(send_telegram(
            "<b>🏆 GOLD SMASHED TP3 ✅✅✅✅✅</b>\n\n"
            "☑️ ALL TARGETS HIT!\n\n"
            "💰 Full profits secured.\n\n"
            "👏 Well done team!",
            reply_markup=join_button()
        ),)).start()
        active_trades[pair] = None
        return jsonify({"status": "tp3_sent"}), 200

    # ── SL ───────────────────────────────────────────────────
    if event == "SL":
        threading.Thread(target=run_async, args=(send_telegram(
            "<b>🛑 GOLD SL HIT</b>\n\n"
            "❌ Stop Loss has been reached\n\n"
            "☑️ Close your positions and wait for next signal"
        ),)).start()
        active_trades[pair] = None
        return jsonify({"status": "sl_sent"}), 200

    # ── BREAK EVEN (silent) ───────────────────────────────────
    if event == "BE":
        active_trades[pair] = None
        return jsonify({"status": "be_cleared"}), 200

    # ── NEW ENTRY SIGNAL ─────────────────────────────────────
    signal = data.get("signal", "").upper()

    if active_trades.get(pair) is not None:
        return jsonify({"status": "ignored", "reason": f"{pair} trade already active"}), 200

    if signal == "BUY":
        emoji      = "🟢"
        entry_low  = round(price - er, 2)
        entry_high = round(price, 2)
        tp1        = round(price + config["tp1"], 2)
        tp2        = round(price + config["tp2"], 2)
        tp3        = round(price + config["tp3"], 2)
        sl         = round(entry_low - config["sl"], 2)
    elif signal == "SELL":
        emoji      = "🔴"
        entry_low  = round(price, 2)
        entry_high = round(price + er, 2)
        tp1        = round(price - config["tp1"], 2)
        tp2        = round(price - config["tp2"], 2)
        tp3        = round(price - config["tp3"], 2)
        sl         = round(entry_high + config["sl"], 2)
    else:
        return jsonify({"error": "Invalid signal"}), 400

    active_trades[pair] = signal

    message = (
        f"{emoji} <b>{signal}</b>\n"
        f"<b>{config['name']}</b>\n\n"
        f"ENTRY : {entry_low} – {entry_high}\n\n"
        f"✅ TP1 {tp1}\n"
        f"✅ TP2 {tp2}\n"
        f"✅ TP3 {tp3}\n"
        f"🛑 SL {sl}\n\n"
        f"<i>(Use Appropriate Lot Sizes)</i>"
    )

    threading.Thread(target=run_async, args=(send_telegram(message),)).start()
    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def home():
    return "Kevin Gold Signals Bot is running! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
