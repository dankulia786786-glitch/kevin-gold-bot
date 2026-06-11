import os
import json
import logging
from flask import Flask, request, jsonify
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
OWNER_ID = os.environ.get("OWNER_ID", "8842842151")
PM_BOT = "https://t.me/Test_indicator01_bot"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Track active trades per pair
active_trades = {}

# Pair config
PAIR_CONFIG = {
    "XAUUSD": {
        "name": "XAU/USD | GOLD",
        "entry_range": 2,
        "tp1": 4, "tp2": 6, "tp3": 10,
        "sl": 8,
        "tps": 3
    },
    "BTCUSD": {
        "name": "BTC/USD | BITCOIN",
        "entry_range": 300,
        "tp1": 150, "tp2": 150, "tp3": 150,
        "sl": 1000,
        "tps": 1
    },
    "US30": {
        "name": "US30 | DOW JONES",
        "entry_range": 20,
        "tp1": 30, "tp2": 50, "tp3": 100,
        "sl": 80,
        "tps": 3
    },
    "USOIL": {
        "name": "USOIL | OIL",
        "entry_range": 0.5,
        "tp1": 0.5, "tp2": 1.0, "tp3": 2.0,
        "sl": 1.5,
        "tps": 3
    }
}

def send_message(text, reply_markup=None, parse_mode="HTML"):
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json=data, timeout=10)
        logger.info(f"Sent message: {r.status_code} {r.text}")
        return r.json()
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

def send_to_owner(text):
    data = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json=data, timeout=10)
    except Exception as e:
        logger.error(f"Error sending to owner: {e}")

def pm_button():
    return {
        "inline_keyboard": [[
            {"text": "👉 JOIN PM NOW FOR FREE! 👈", "url": PM_BOT}
        ]]
    }

def format_price(pair, price):
    if pair == "BTCUSD" or pair == "US30":
        return f"{price:,.0f}"
    elif pair == "USOIL":
        return f"{price:.2f}"
    else:
        return f"{price:.2f}"

def handle_entry(pair, direction, price):
    config = PAIR_CONFIG.get(pair, PAIR_CONFIG["XAUUSD"])
    price = float(price)
    er = config["entry_range"]

    if direction == "BUY":
        entry_low = price - er
        entry_high = price
        tp1 = price + config["tp1"]
        tp2 = price + config["tp2"]
        tp3 = price + config["tp3"]
        sl = entry_low - config["sl"]
        emoji = "🟢"
    else:
        entry_low = price
        entry_high = price + er
        tp1 = price - config["tp1"]
        tp2 = price - config["tp2"]
        tp3 = price - config["tp3"]
        sl = entry_high + config["sl"]
        emoji = "🔴"

    active_trades[pair] = {
        "direction": direction,
        "entry": price,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "sl": sl,
        "tp1_hit": False, "tp2_hit": False
    }

    fp = lambda p: format_price(pair, p)

    if config["tps"] == 1:
        text = (
            f"{emoji} <b>{direction}</b>\n"
            f"<b>{config['name']}</b>\n\n"
            f"ENTRY : {fp(entry_low)} – {fp(entry_high)}\n\n"
            f"✅ TP1 {fp(tp1)}\n"
            f"🛑 SL {fp(sl)}\n\n"
            f"(Use Appropriate Lot Sizes)"
        )
    else:
        text = (
            f"{emoji} <b>{direction}</b>\n"
            f"<b>{config['name']}</b>\n\n"
            f"ENTRY : {fp(entry_low)} – {fp(entry_high)}\n\n"
            f"✅ TP1 {fp(tp1)}\n"
            f"✅ TP2 {fp(tp2)}\n"
            f"✅ TP3 {fp(tp3)}\n"
            f"🛑 SL {fp(sl)}\n\n"
            f"(Use Appropriate Lot Sizes)"
        )

    send_message(text)

def handle_tp(pair, tp_num):
    config = PAIR_CONFIG.get(pair, PAIR_CONFIG["XAUUSD"])
    label = config["name"].split("|")[1].strip()

    if tp_num == 1:
        if config["tps"] == 1:
            text = (
                f"<b>🏆 {label} SMASHED TP1 ✅✅✅</b>\n\n"
                f"☑️ ALL TARGETS HIT!\n\n"
                f"💰 Full profits secured.\n\n"
                f"👏 Well done team!"
            )
            active_trades.pop(pair, None)
            send_message(text, reply_markup=pm_button())
        else:
            text = (
                f"<b>🏅 {label} SMASHED TP1 ✅✅✅</b>\n\n"
                f"☑️ Close your positions now and secure your profits\n\n"
                f"Or\n\n"
                f"☑️ Move your SL to Break Even and let the trade run risk free"
            )
            if pair in active_trades:
                active_trades[pair]["tp1_hit"] = True
            send_message(text, reply_markup=pm_button())

    elif tp_num == 2:
        text = (
            f"<b>🏅 {label} SMASHED TP2 ✅✅✅✅</b>\n\n"
            f"☑️ Close remaining positions and secure your profits\n\n"
            f"Or\n\n"
            f"☑️ Let the remaining trade run risk free to TP3"
        )
        if pair in active_trades:
            active_trades[pair]["tp2_hit"] = True
        send_message(text, reply_markup=pm_button())

    elif tp_num == 3:
        text = (
            f"<b>🏆 {label} SMASHED TP3 ✅✅✅✅✅</b>\n\n"
            f"☑️ ALL TARGETS HIT!\n\n"
            f"💰 Full profits secured.\n\n"
            f"👏 Well done team!"
        )
        active_trades.pop(pair, None)
        send_message(text, reply_markup=pm_button())

def handle_sl(pair):
    active_trades.pop(pair, None)
    text = (
        f"<b>SL Triggered Team ❌</b>\n\n"
        f"Looking for the next Set-Up. Lets win on the Next one!"
    )
    send_message(text)

def handle_breakeven(pair):
    active_trades.pop(pair, None)
    logger.info(f"Break even hit for {pair} — trade cleared silently")

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        logger.info(f"Received: {data}")

        event = data.get("event", "")
        direction = data.get("direction", "").upper()
        price = data.get("price", 0)
        pair = data.get("pair", "XAUUSD").upper()

        signal = data.get("signal", "").upper()
        if signal in ["BUY", "SELL"] and not event:
            event = "entry"
            direction = signal

        if event == "entry":
            if pair not in active_trades:
                handle_entry(pair, direction, price)
            else:
                logger.info(f"Trade already active for {pair} — ignoring new signal")

        elif event == "TP1":
            handle_tp(pair, 1)
        elif event == "TP2":
            handle_tp(pair, 2)
        elif event == "TP3":
            handle_tp(pair, 3)
        elif event == "SL":
            handle_sl(pair)
        elif event == "BE":
            handle_breakeven(pair)

        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/telegram_update", methods=["POST"])
def telegram_update():
    try:
        data = request.get_json(force=True)
        message = data.get("message", {})
        if message:
            user = message.get("from", {})
            name = user.get("first_name", "Unknown")
            username = user.get("username", "no username")
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")

            if chat_id:
                requests.post(f"{TELEGRAM_API}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "Hi! Kevin will message you shortly! 🏆"
                }, timeout=10)

            send_to_owner(
                f"📩 New PM request!\n\n"
                f"Name: {name}\n"
                f"Username: @{username}\n"
                f"Message: {text}\n\n"
                f"<a href='tg://user?id={user.get('id')}'>Reply to them</a>"
            )

        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Telegram update error: {e}")
        return jsonify({"ok": False}), 500

@app.route("/", methods=["GET"])
def home():
    return "Kevin Gold Signals Bot is running! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
