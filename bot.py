import os
import json
import logging
import threading
import time
import requests
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN")
CHAT_ID    = os.environ.get("CHAT_ID")
CHAT_ID_2  = os.environ.get("CHAT_ID_2", "")
OWNER_ID   = os.environ.get("OWNER_ID", "8842842151")

# Triple state backup — all three written on every save
STATE_FILES = [
    "/tmp/trade_state.json",
    "/tmp/trade_state_b1.json",
    "/tmp/trade_state_b2.json"
]

TELEGRAM_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHART_IMG_KEY  = os.environ.get("CHART_IMG_KEY", "")
state_lock     = threading.Lock()

# ─── CHART IMAGE ─────────────────────────────────────────────────────────────

def get_chart_image(pair):
    if not CHART_IMG_KEY:
        return None
    try:
        symbol = "OANDA:XAUUSD" if pair == "XAUUSD" else "BITSTAMP:BTCUSD"
        url = (
            f"https://api.chart-img.com/v1/tradingview/advanced-chart"
            f"?symbol={symbol}&interval=5m&theme=dark"
            f"&studies=RSI,Volume"
            f"&key={CHART_IMG_KEY}"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            return r.content
        logger.warning(f"Chart image failed: {r.status_code}")
    except Exception as e:
        logger.error(f"Chart image error: {e}")
    return None

def send_photo_to_channel(chat_id, photo_bytes, caption):
    try:
        files = {"photo": ("chart.png", photo_bytes, "image/png")}
        data  = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(f"{TELEGRAM_URL}/sendPhoto", files=files, data=data, timeout=15)
        result = r.json()
        if result.get("ok"):
            return result["result"]["message_id"]
    except Exception as e:
        logger.error(f"sendPhoto error: {e}")
    return None

def send_signal_with_chart(text, pair):
    channels = [c for c in [CHAT_ID, CHAT_ID_2] if c]
    msg_ids  = {}
    chart    = get_chart_image(pair)
    for ch in channels:
        if chart:
            mid = send_photo_to_channel(ch, chart, text)
        else:
            mid = send_to_channel(ch, text)
        if mid:
            msg_ids[ch] = mid
    return msg_ids

# ─── STATE ───────────────────────────────────────────────────────────────────

def load_state():
    for path in STATE_FILES:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "XAUUSD" in data:
                    logger.info(f"State loaded from {path}")
                    return data
        except Exception as e:
            logger.warning(f"State load failed {path}: {e}")
    return {"XAUUSD": None, "BTCUSD": None}

def save_state(state):
    payload = json.dumps(state)
    for path in STATE_FILES:
        try:
            with open(path, "w") as f:
                f.write(payload)
        except Exception as e:
            logger.error(f"State save failed {path}: {e}")

active_trades = load_state()

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def send_to_channel(chat_id, text, reply_to=None, keyboard=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    try:
        r = requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload, timeout=10)
        data = r.json()
        if data.get("ok"):
            return data["result"]["message_id"]
        logger.error(f"Telegram rejected message to {chat_id}: {data}")
    except Exception as e:
        logger.error(f"Send error to {chat_id}: {e}")
    return None

def send_message(text, reply_to_ids=None, keyboard=None):
    """Send to all channels. reply_to_ids = {chat_id: message_id}"""
    channels = [c for c in [CHAT_ID, CHAT_ID_2] if c]
    msg_ids  = {}
    for ch in channels:
        reply_to = (reply_to_ids or {}).get(ch)
        mid = send_to_channel(ch, text, reply_to=reply_to, keyboard=keyboard)
        if mid:
            msg_ids[ch] = mid
    return msg_ids

def notify_owner(text):
    try:
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={
            "chat_id": OWNER_ID, "text": text, "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        logger.error(f"Owner notify error: {e}")

JOIN_BUTTON = {
    "inline_keyboard": [[{
        "text": "👉 JOIN PM NOW FOR FREE! 👈",
        "url": "https://t.me/Test_indicator01_bot"
    }]]
}

# ─── PRICE FETCHING — 3 sources each, fastest first ─────────────────────────

def get_price_gold():
    # 1. Twelve Data — real-time XAUUSD in USD
    try:
        td_key = os.environ.get("TWELVE_DATA_KEY", "")
        if td_key:
            r = requests.get(
                f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={td_key}",
                timeout=5
            )
            if r.status_code == 200:
                p = float(r.json().get("price", 0))
                if p > 3000:  # Sanity check — Gold must be above $3000
                    logger.info(f"Gold via TwelveData: {p}")
                    return p
    except Exception:
        pass

    # 2. Frankfurter via Gold API — returns USD per troy oz
    try:
        r = requests.get(
            "https://api.gold-api.com/price/XAU",
            timeout=6
        )
        if r.status_code == 200:
            p = float(r.json().get("price", 0))
            if p > 3000:
                logger.info(f"Gold via gold-api.com: {p}")
                return p
    except Exception:
        pass

    # 3. Metals.live — but validate it's USD (must be > 3000)
    try:
        r = requests.get("https://api.metals.live/v1/spot/gold", timeout=6)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                p = float(data[0].get("gold", 0))
                if p > 3000:  # Only accept if looks like USD price
                    logger.info(f"Gold via metals.live: {p}")
                    return p
    except Exception:
        pass

    return None

def get_price_btc():
    # 1. Binance — fastest, direct exchange
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
            timeout=5
        )
        if r.status_code == 200:
            p = float(r.json()["price"])
            if p > 0:
                logger.debug(f"BTC via Binance: {p}")
                return p
    except Exception:
        pass

    # 2. CoinGecko — reliable free API
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
            timeout=6
        )
        if r.status_code == 200:
            p = float(r.json()["bitcoin"]["usd"])
            if p > 0:
                logger.debug(f"BTC via CoinGecko: {p}")
                return p
    except Exception:
        pass

    # 3. Coinbase — second exchange fallback
    try:
        r = requests.get(
            "https://api.coinbase.com/v2/prices/BTC-USD/spot",
            timeout=6
        )
        if r.status_code == 200:
            p = float(r.json()["data"]["amount"])
            if p > 0:
                logger.debug(f"BTC via Coinbase: {p}")
                return p
    except Exception:
        pass

    return None

def get_price(pair):
    return get_price_gold() if pair == "XAUUSD" else get_price_btc()

# ─── TP / SL MESSAGES ────────────────────────────────────────────────────────

def send_tp_message(pair, tp_num, signal_ids):
    if pair == "XAUUSD":
        if tp_num == 1:
            text = (
                "<b>GOLD SMASHED TP1 ✅✅✅</b>\n\n"
                "☑️ Close your positions now and secure your profits\n\n"
                "Or\n\n"
                "☑️ Move your SL to Break Even and let the trade run risk free"
            )
        elif tp_num == 2:
            text = (
                "<b>GOLD SMASHED TP2 ✅✅✅✅</b>\n\n"
                "☑️ Close remaining positions and secure your profits\n\n"
                "Or\n\n"
                "☑️ Let the remaining trade run risk free to TP3"
            )
        else:
            text = (
                "<b>GOLD SMASHED TP3 ✅✅✅✅✅</b>\n\n"
                "☑️ ALL TARGETS HIT!\n\n"
                "💰 Full profits secured.\n\n"
                "👏 Well done team!"
            )
    else:
        text = (
            "<b>BITCOIN SMASHED TP1 ✅✅✅</b>\n\n"
            "☑️ ALL TARGETS HIT!\n\n"
            "💰 Full profits secured.\n\n"
            "👏 Well done team!"
        )
    send_message(text, reply_to_ids=signal_ids, keyboard=JOIN_BUTTON)

def send_sl_message(pair, signal_ids):
    text = "SL Triggered Team ❌\nLooking for the next Set-Up. Lets win on the Next one!"
    send_message(text, reply_to_ids=signal_ids)

# ─── PRICE MONITOR ───────────────────────────────────────────────────────────

def price_monitor():
    logger.info("Price monitor started — 30 second intervals")
    fail_counts = {"XAUUSD": 0, "BTCUSD": 0}

    while True:
        try:
            with state_lock:
                snapshot = json.loads(json.dumps(active_trades))

            for pair, trade in snapshot.items():
                if trade is None:
                    fail_counts[pair] = 0
                    continue

                price = get_price(pair)

                if price is None:
                    fail_counts[pair] += 1
                    logger.warning(f"All price sources failed for {pair} — count: {fail_counts[pair]}")
                    if fail_counts[pair] == 10:  # 5 minutes of failures
                        notify_owner(
                            f"⚠️ ALERT: Cannot fetch {pair} price for 5 minutes.\n"
                            f"All 3 price sources are down.\n"
                            f"Bot is running but cannot monitor TP/SL.\n"
                            f"Check Railway logs."
                        )
                    continue

                fail_counts[pair] = 0
                direction    = trade["direction"]
                tp_levels    = trade["tp_levels"]
                sl           = trade["sl"]
                be           = trade.get("be")
                signal_ids   = trade.get("signal_msg_ids", {})
                tp_hit_count = trade.get("tp_hit_count", 0)

                hit_tp = hit_sl = hit_be = False

                if direction == "BUY":
                    if tp_levels and price >= tp_levels[0]:
                        hit_tp = True
                    elif price <= sl:
                        hit_sl = True
                    elif be is not None and price <= be and tp_hit_count > 0:
                        hit_be = True
                else:
                    if tp_levels and price <= tp_levels[0]:
                        hit_tp = True
                    elif price >= sl:
                        hit_sl = True
                    elif be is not None and price >= be and tp_hit_count > 0:
                        hit_be = True

                if hit_tp:
                    tp_num = tp_hit_count + 1
                    logger.info(f"✅ {pair} TP{tp_num} HIT @ {price}")
                    send_tp_message(pair, tp_num, signal_ids)
                    remaining = tp_levels[1:]
                    with state_lock:
                        if active_trades[pair]:
                            active_trades[pair]["tp_levels"]    = remaining
                            active_trades[pair]["tp_hit_count"] = tp_num
                            if pair == "XAUUSD" and tp_num == 1:
                                active_trades[pair]["be"] = trade["entry_mid"]
                            if not remaining:
                                active_trades[pair] = None
                            save_state(active_trades)

                elif hit_sl:
                    logger.info(f"❌ {pair} SL HIT @ {price}")
                    send_sl_message(pair, signal_ids)
                    with state_lock:
                        active_trades[pair] = None
                        save_state(active_trades)

                elif hit_be:
                    logger.info(f"↩️ {pair} BE HIT @ {price} — silent clear")
                    with state_lock:
                        active_trades[pair] = None
                        save_state(active_trades)

        except Exception as e:
            logger.error(f"Monitor error: {e}")

        time.sleep(30)

# ─── WEBHOOK ─────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data      = request.get_json(force=True)
        event     = data.get("event")
        pair      = data.get("pair", "XAUUSD")
        direction = data.get("direction", "BUY").upper()
        price     = float(str(data.get("price", "0")).replace(",", ""))

        logger.info(f"Webhook: {event} | {pair} | {direction} | {price}")

        if event == "entry":
            with state_lock:
                if active_trades.get(pair) is not None:
                    return jsonify({"status": "ignored", "reason": "trade active"})

            if pair == "XAUUSD":
                entry_low  = round(price - 2, 2)
                entry_high = round(price, 2)
                entry_mid  = price
                tp1 = round(price + 2, 2)  if direction == "BUY" else round(price - 2, 2)
                tp2 = round(price + 3, 2)  if direction == "BUY" else round(price - 3, 2)
                tp3 = round(price + 10, 2) if direction == "BUY" else round(price - 10, 2)
                sl  = round(price - 12, 2) if direction == "BUY" else round(price + 12, 2)
                tp_levels = [tp1, tp2, tp3]
                emoji = "🟢" if direction == "BUY" else "🔴"
                text = (
                    f"{emoji} <b>{direction}\n"
                    f"XAU/USD | GOLD</b>\n\n"
                    f"ENTRY : {entry_low:.2f} – {entry_high:.2f}\n\n"
                    f"✅ TP1 {tp1:.2f}\n"
                    f"✅ TP2 {tp2:.2f}\n"
                    f"✅ TP3 {tp3:.2f}\n"
                    f"🚫 SL {sl:.2f}\n\n"
                    f"(Use Appropriate Lot Sizes)"
                )
            else:
                entry_low  = int(price - 150)
                entry_high = int(price)
                entry_mid  = price
                tp1 = int(price + 100) if direction == "BUY" else int(price - 100)
                sl  = int(price - 1000) if direction == "BUY" else int(price + 1000)
                tp_levels = [tp1]
                emoji = "🟢" if direction == "BUY" else "🔴"
                text = (
                    f"{emoji} <b>{direction}</b>\n"
                    f"<b>BTC/USD | BITCOIN</b>\n\n"
                    f"ENTRY : {entry_low:,} – {entry_high:,}\n\n"
                    f"✅ TP1 {tp1:,}\n"
                    f"🛑 SL {sl:,}\n\n"
                    f"(Use Appropriate Lot Sizes)"
                )

            signal_ids = send_signal_with_chart(text, pair)
            logger.info(f"Entry sent — msg_ids: {signal_ids}")

            with state_lock:
                active_trades[pair] = {
                    "direction":      direction,
                    "entry_mid":      entry_mid,
                    "tp_levels":      tp_levels,
                    "sl":             sl,
                    "be":             None,
                    "tp_hit_count":   0,
                    "signal_msg_ids": signal_ids
                }
                save_state(active_trades)

            return jsonify({"status": "ok", "signal_msg_ids": signal_ids})

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ─── TELEGRAM UPDATES ────────────────────────────────────────────────────────

@app.route("/telegram_update", methods=["POST"])
def telegram_update():
    try:
        update  = request.get_json(force=True)
        message = update.get("message", {})
        if not message:
            return jsonify({"ok": True})
        user     = message.get("from", {})
        text     = message.get("text", "")
        name     = user.get("first_name", "Unknown")
        username = user.get("username", "no username")
        notify_owner(
            f"📩 New PM via bot:\n"
            f"Name: {name}\n"
            f"Username: @{username}\n"
            f"Message: {text}"
        )
    except Exception as e:
        logger.error(f"Telegram update error: {e}")
    return jsonify({"ok": True})

# ─── HEALTH ──────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    with state_lock:
        gold = active_trades.get("XAUUSD")
        btc  = active_trades.get("BTCUSD")
    ch2_info = f" | Channel 2: {CHAT_ID_2}" if CHAT_ID_2 else " | Channel 2: not set"
    return (
        f"Kevin Gold Signals Bot is running! ✅\n"
        f"Channel 1: {CHAT_ID}{ch2_info}\n"
        f"Gold trade active: {'Yes' if gold else 'No'}\n"
        f"Bitcoin trade active: {'Yes' if btc else 'No'}\n"
        f"Price monitor: Running every 30s\n"
        f"State backups: 3 files"
    )

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=price_monitor, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
