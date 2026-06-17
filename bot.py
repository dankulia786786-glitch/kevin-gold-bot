import os
import json
import logging
import threading
import time
import random
import textwrap
import datetime
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN")
CHAT_ID    = os.environ.get("CHAT_ID")
CHAT_ID_2  = os.environ.get("CHAT_ID_2", "")
OWNER_ID   = os.environ.get("OWNER_ID", "8842842151")

STATE_FILES = [
    "/data/trade_state.json",
    "/data/trade_state_b1.json",
    "/data/trade_state_b2.json"
]

TELEGRAM_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHART_IMG_KEY  = os.environ.get("CHART_IMG_KEY", "")
state_lock     = threading.Lock()

# ─── DAILY MOTIVATIONAL QUOTE ────────────────────────────────────────────────
QUOTE_AUTHOR = "Kevin Burns & Team"
QUOTE_STATE_FILE = "/data/quote_state.json"

# Background images live in this folder next to bot.py on GitHub.
# bg_01.jpg ... bg_10.jpg — Kevin's own lifestyle photos.
QUOTE_BG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quote_bg")
QUOTE_BG_FILES = [f"bg_{i:02d}.jpg" for i in range(1, 11)]

MOTIVATIONAL_QUOTES = [
    "The stock market is a device for transferring money from the impatient to the patient.",
    "Risk comes from not knowing what you're doing.",
    "The best investment you can make is in yourself.",
    "Price is what you pay. Value is what you get.",
    "Someone is sitting in the shade today because someone planted a tree long ago.",
    "Do not save what is left after spending, but spend what is left after saving.",
    "In investing, what is comfortable is rarely profitable.",
    "The four most dangerous words in investing are: this time it's different.",
    "Wide diversification is only required when investors do not understand what they are doing.",
    "It's not how much money you make, but how much money you keep.",
    "The individual investor should act consistently as an investor and not as a speculator.",
    "Know what you own, and know why you own it.",
    "The time to buy is when there's blood in the streets.",
    "Compound interest is the eighth wonder of the world.",
    "An investment in knowledge pays the best interest.",
    "The more you learn, the more you earn.",
    "Financial freedom is available to those who learn about it and work for it.",
    "A second income is not a luxury. It is a necessity.",
    "Don't work for money. Make money work for you.",
    "The secret to wealth is simple: spend less than you earn and invest the rest.",
    "Investing is laying out money now to get more money back in the future.",
    "The stock market is filled with individuals who know the price of everything but the value of nothing.",
    "Never depend on a single income. Make investment to create a second source.",
    "Money is a terrible master but an excellent servant.",
    "The goal of investing is to find situations where it is safe to be non-diversified.",
    "Wealth is not about having a lot of money; it's about having a lot of options.",
    "Success in investing doesn't correlate with IQ. What you need is the temperament.",
    "Every pound you invest today is a soldier working for your future.",
    "The best time to invest was yesterday. The second best time is today.",
    "Trading is a skill. Investing is a discipline. Master both.",
    "A budget is telling your money where to go instead of wondering where it went.",
    "Build assets, not liabilities. That is the game of the wealthy.",
    "Your income is not your wealth. Your savings rate is.",
    "The wealthy invest first and spend what remains.",
    "Small consistent investments today create enormous wealth tomorrow.",
    "Markets fluctuate. Discipline doesn't have to.",
    "Patience is the most valuable commodity in the financial markets.",
    "The difference between the rich and everyone else is what they do with their money after they earn it.",
    "Capital grows when you protect it first and grow it second.",
    "A man who stops advertising to save money is like a man who stops a clock to save time.",
    "Real wealth is passive income exceeding your expenses.",
    "Opportunities come infrequently. When it rains gold, put out the bucket.",
    "Buy when everyone is selling. Sell when everyone is buying.",
    "The intelligent investor is a realist who sells to optimists and buys from pessimists.",
    "Your financial future is built one smart decision at a time.",
    "Money is like a seed. Plant it wisely and it will grow beyond what you imagined.",
    "Time in the market beats timing the market.",
    "The wealthy don't earn more. They retain more and deploy it wisely.",
    "Trading without a plan is gambling. Plan your trade, trade your plan.",
    "A rising tide lifts all boats. Position yourself in the right waters.",
    "Diversify your income. One stream can dry up. Many streams become a river.",
    "The greatest returns come from those with the longest time horizons.",
    "Economic cycles repeat. Position yourself ahead of the next one.",
    "Control your emotions or the market will control your account.",
    "Capital preservation is the first rule of wealth building.",
    "Never invest money you cannot afford to lose. Never fail to invest money you can.",
    "The market rewards research, discipline, and patience above all else.",
    "Wealth is built quietly, one correct decision at a time.",
    "Start small. Stay consistent. Think long term. That is the formula.",
    "True financial freedom is waking up without an alarm and still being paid.",
]


def get_quote_state():
    try:
        if os.path.exists(QUOTE_STATE_FILE):
            with open(QUOTE_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"used_quote_indices": [], "used_bg_indices": [], "last_sent_date": None}


def save_quote_state(state):
    try:
        with open(QUOTE_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Quote state save failed: {e}")


def pick_daily_quote():
    state = get_quote_state()
    used = state.get("used_quote_indices", [])
    available = [i for i in range(len(MOTIVATIONAL_QUOTES)) if i not in used]
    if not available:
        used = []
        available = list(range(len(MOTIVATIONAL_QUOTES)))
    idx = random.choice(available)
    used.append(idx)
    state["used_quote_indices"] = used
    save_quote_state(state)
    return MOTIVATIONAL_QUOTES[idx]


def pick_daily_bg():
    state = get_quote_state()
    used = state.get("used_bg_indices", [])
    available = [i for i in range(len(QUOTE_BG_FILES)) if i not in used]
    if not available:
        used = []
        available = list(range(len(QUOTE_BG_FILES)))
    idx = random.choice(available)
    used.append(idx)
    state["used_bg_indices"] = used
    save_quote_state(state)
    return os.path.join(QUOTE_BG_DIR, QUOTE_BG_FILES[idx])


FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
BUNDLED_BOLD_FONT = os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf")

_font_warning_logged = False


def find_font(bold=True, size=54):
    """
    Loads the bold font bundled in the repo's /fonts folder. This is
    deliberate — Railway's container does NOT have system fonts like
    DejaVu or Liberation installed by default. Relying on system font
    paths silently fell back to PIL's tiny built-in default font on
    Railway, which is why text looked fine in testing but came out
    tiny in the real Telegram channel. Shipping the .ttf file directly
    in the repo removes that dependency entirely.
    """
    global _font_warning_logged
    try:
        if os.path.exists(BUNDLED_BOLD_FONT):
            return ImageFont.truetype(BUNDLED_BOLD_FONT, size)
    except Exception as e:
        logger.error(f"Bundled font failed to load: {e}")

    # Fallback to system fonts only if the bundled one is somehow missing
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue

    if not _font_warning_logged:
        logger.error(
            "⚠️ NO BOLD FONT FOUND ANYWHERE — quote text will render tiny. "
            "Check that fonts/DejaVuSans-Bold.ttf was uploaded to GitHub."
        )
        _font_warning_logged = True
    return ImageFont.load_default()


def generate_quote_image(quote, author=QUOTE_AUTHOR, bg_path=None):
    """
    Overlays a bold quote + author name on top of one of Kevin's own
    lifestyle photos (bg_01.jpg ... bg_10.jpg). A dark gradient band is
    drawn behind the text zone so it stays readable regardless of how
    light, dark, or busy the underlying photo is.
    """
    if bg_path is None or not os.path.exists(bg_path):
        # Fallback so the bot never crashes even if a file is missing
        W, H = 1080, 1080
        img = Image.new("RGB", (W, H), (15, 15, 18))
    else:
        img = Image.open(bg_path).convert("RGB")
        W, H = img.size

    # Slightly darken the whole photo so white text always has contrast
    overlay_dark = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(img, overlay_dark, 0.18)

    # Dark gradient band behind the text zone (middle third of the image)
    band = Image.new("L", (W, H), 0)
    bdraw = ImageDraw.Draw(band)
    band_top = int(H * 0.30)
    band_bottom = int(H * 0.62)
    fade = int(H * 0.08)
    for y in range(max(0, band_top - fade), min(H, band_bottom + fade)):
        if y < band_top:
            alpha = int(190 * ((y - (band_top - fade)) / fade)) if fade else 190
        elif y > band_bottom:
            alpha = int(190 * (1 - (y - band_bottom) / fade)) if fade else 190
        else:
            alpha = 190
        alpha = max(0, min(190, alpha))
        bdraw.line([(0, y), (W, y)], fill=alpha)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, band)

    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 10], fill=(212, 175, 55))

    quote_upper = quote.upper()
    font_size = 80
    max_width_chars = 16
    font_quote = find_font(bold=True, size=font_size)
    lines = textwrap.fill(quote_upper, width=max_width_chars).split("\n")

    band_center = (band_top + band_bottom) // 2
    while True:
        line_height = int(font_size * 1.2)
        total_h = len(lines) * line_height
        if total_h < (band_bottom - band_top) - 20 or font_size <= 48:
            break
        font_size -= 4
        font_quote = find_font(bold=True, size=font_size)
        lines = textwrap.fill(quote_upper, width=max_width_chars).split("\n")

    line_height = int(font_size * 1.2)
    total_h = len(lines) * line_height
    y = band_center - total_h // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_quote)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) // 2 + 4, y + 4), line, font=font_quote, fill=(0, 0, 0))
        draw.text(((W - w) // 2, y), line, font=font_quote, fill=(255, 255, 255))
        y += line_height

    draw.line([(W // 2 - 80, y + 35), (W // 2 + 80, y + 35)], fill=(212, 175, 55), width=5)
    font_author = find_font(bold=True, size=36)
    author_text = author.upper()
    bbox = draw.textbbox((0, 0), author_text, font=font_author)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) // 2, y + 55), author_text, font=font_author, fill=(212, 175, 55))

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf.read()


def send_daily_quote():
    try:
        quote = pick_daily_quote()
        bg_path = pick_daily_bg()
        image_bytes = generate_quote_image(quote, bg_path=bg_path)
        channels = [c for c in [CHAT_ID, CHAT_ID_2] if c]
        caption = "🔔 <b>Unmute &amp; Pin this channel to never miss a signal!</b>"
        for ch in channels:
            send_photo_to_channel(ch, image_bytes, caption)
        logger.info(f"Daily quote sent: {quote[:40]}... | bg={os.path.basename(bg_path)}")
    except Exception as e:
        logger.error(f"Daily quote error: {e}")


def quote_scheduler():
    logger.info("Quote scheduler started — checking every 30s for 08:00 UK time")
    while True:
        try:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # UK summer time (UTC+1)
            today_str = now.strftime("%Y-%m-%d")
            if now.hour == 8 and now.minute == 0:
                state = get_quote_state()
                if state.get("last_sent_date") != today_str:
                    send_daily_quote()
                    state = get_quote_state()
                    state["last_sent_date"] = today_str
                    save_quote_state(state)
        except Exception as e:
            logger.error(f"Quote scheduler error: {e}")
        time.sleep(30)


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
        logger.error(f"sendPhoto rejected: {result}")
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
last_entry_time = {}


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


# ─── PRICE FETCHING ──────────────────────────────────────────────────────────
def get_price_gold():
    try:
        td_key = os.environ.get("TWELVE_DATA_KEY", "")
        if td_key:
            r = requests.get(f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={td_key}", timeout=5)
            if r.status_code == 200:
                p = float(r.json().get("price", 0))
                if p > 3000:
                    return p
    except Exception:
        pass
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=6)
        if r.status_code == 200:
            p = float(r.json().get("price", 0))
            if p > 3000:
                return p
    except Exception:
        pass
    try:
        r = requests.get("https://api.metals.live/v1/spot/gold", timeout=6)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                p = float(data[0].get("gold", 0))
                if p > 3000:
                    return p
    except Exception:
        pass
    return None


def get_price_btc():
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
        if r.status_code == 200:
            p = float(r.json()["price"])
            if p > 0:
                return p
    except Exception:
        pass
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", timeout=6)
        if r.status_code == 200:
            p = float(r.json()["bitcoin"]["usd"])
            if p > 0:
                return p
    except Exception:
        pass
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=6)
        if r.status_code == 200:
            p = float(r.json()["data"]["amount"])
            if p > 0:
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
                    if fail_counts[pair] == 10:
                        notify_owner(f"⚠️ ALERT: Cannot fetch {pair} price for 5 minutes.")
                    continue
                fail_counts[pair] = 0
                direction    = trade["direction"]
                tp_levels    = trade["tp_levels"]
                sl           = trade["sl"]
                be           = trade.get("be")
                signal_ids   = trade.get("signal_msg_ids", {})
                tp_hit_count = trade.get("tp_hit_count", 0)

                hit_tp = hit_sl = hit_be = False
                SL_BUFFER = 6.0   # Twelve Data API runs ~5-6pts above real broker price
                BE_BUFFER = 6.0
                if direction == "BUY":
                    if tp_levels and price >= tp_levels[0]:
                        hit_tp = True
                    elif price <= sl + SL_BUFFER:
                        hit_sl = True
                    elif be is not None and price <= be + BE_BUFFER and tp_hit_count > 0:
                        hit_be = True
                else:
                    if tp_levels and price <= tp_levels[0]:
                        hit_tp = True
                    elif price >= sl - SL_BUFFER:
                        hit_sl = True
                    elif be is not None and price >= be - BE_BUFFER and tp_hit_count > 0:
                        hit_be = True

                if hit_tp:
                    tp_num = tp_hit_count + 1
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
                    send_sl_message(pair, signal_ids)
                    with state_lock:
                        active_trades[pair] = None
                        save_state(active_trades)
                elif hit_be:
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
            now = time.time()
            with state_lock:
                if active_trades.get(pair) is not None:
                    return jsonify({"status": "ignored", "reason": "trade active"})
                last_entry = last_entry_time.get(pair, 0)
                if now - last_entry < 60:
                    logger.warning(f"Duplicate entry for {pair} ignored — last one {now - last_entry:.1f}s ago")
                    return jsonify({"status": "ignored", "reason": "duplicate within 60s"})
                last_entry_time[pair] = now

            if pair == "XAUUSD":
                if direction == "BUY":
                    entry_low  = round(price - 1, 2)
                    entry_high = round(price + 2, 2)
                    tp1 = round(price + 4, 2)
                    tp2 = round(price + 5, 2)
                    tp3 = round(price + 12, 2)
                    sl  = round(price - 11, 2)
                else:
                    entry_low  = round(price - 2, 2)
                    entry_high = round(price + 1, 2)
                    tp1 = round(price - 4, 2)
                    tp2 = round(price - 5, 2)
                    tp3 = round(price - 12, 2)
                    sl  = round(price + 11, 2)
                entry_mid = price
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
                if direction == "BUY":
                    entry_low  = int(price - 150)
                    entry_high = int(price)
                    tp1 = int(price + 100)
                    sl  = int(price - 1000)
                else:
                    entry_low  = int(price)
                    entry_high = int(price + 150)
                    tp1 = int(price - 100)
                    sl  = int(price + 1000)
                entry_mid = price
                tp_levels = [tp1]
                emoji = "🟢" if direction == "BUY" else "🔴"
                text = (
                    f"{emoji} <b>{direction}\n"
                    f"BTC/USD | BITCOIN</b>\n\n"
                    f"ENTRY : {entry_low:,} – {entry_high:,}\n\n"
                    f"✅ TP1 {tp1:,}\n"
                    f"🚫 SL {sl:,}\n\n"
                    f"(Use Appropriate Lot Sizes)"
                )

            signal_ids = send_signal_with_chart(text, pair)

            # Queue signal for MT5 EA to pick up on next poll
            with mt5_signal_lock:
                mt5_pending_signal.clear()
                mt5_pending_signal.update({
                    "id":        f"{pair}_{int(time.time())}",
                    "pair":      pair,
                    "direction": direction,
                    "entry_mid": entry_mid,
                    "sl":        sl,
                    "tp1":       tp_levels[0] if len(tp_levels) > 0 else 0,
                    "tp2":       tp_levels[1] if len(tp_levels) > 1 else 0,
                    "tp3":       tp_levels[2] if len(tp_levels) > 2 else 0,
                })
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
        notify_owner(f"📩 New PM via bot:\nName: {name}\nUsername: @{username}\nMessage: {text}")
    except Exception as e:
        logger.error(f"Telegram update error: {e}")
    return jsonify({"ok": True})


# Track which TP levels have already been sent per signal — permanent, not time-based
mt5_close_sent = set()
mt5_close_lock = threading.Lock()

@app.route("/mt5_close", methods=["POST"])
def mt5_close():
    """
    Called by the MT5 EA when a position closes.
    Only handles SL — TPs are handled by Railway price monitor (more reliable).
    """
    try:
        data       = request.get_json(force=True)
        pair       = data.get("pair", "XAUUSD")
        close_type = data.get("close_type", "SL")
        price      = float(data.get("price", 0))
        profit     = float(data.get("profit", 0))
        comment    = data.get("comment", "")

        logger.info(f"MT5 close: {pair} {close_type} price={price} profit={profit}")

        # Only handle SL from MT5 — TPs handled by Railway price monitor
        if close_type != "SL":
            logger.info(f"Ignoring {close_type} from MT5 — handled by price monitor")
            return jsonify({"status": "ignored"})

        # SL — use MT5 for instant accurate detection
        text = "SL Triggered Team ❌\nLooking for the next Set-Up. Lets win on the Next one!"

        with state_lock:
            trade_state = active_trades.get(pair)
            signal_ids  = trade_state.get("signal_msg_ids", {}) if trade_state else {}
            active_trades[pair] = None
            save_state(active_trades)

        send_message(text, reply_to_ids=signal_ids)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"mt5_close error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── MT5 SIGNAL ENDPOINT ─────────────────────────────────────────────────────
# The MT5 EA polls this every 5 seconds to check for new signals.
# Returns the latest pending signal once, then clears it so it's not
# re-executed on the next poll.
mt5_pending_signal = {}
mt5_signal_lock = threading.Lock()

@app.route("/mt5_signal", methods=["GET"])
def mt5_signal():
    with mt5_signal_lock:
        if not mt5_pending_signal:
            return "none"
        signal = dict(mt5_pending_signal)
        mt5_pending_signal.clear()
    return jsonify(signal)


# ─── HEALTH ──────────────────────────────────────────────────────────────────
@app.route("/reset", methods=["GET"])
def reset():
    with state_lock:
        active_trades["XAUUSD"] = None
        active_trades["BTCUSD"] = None
        save_state(active_trades)
    return "All trades cleared! ✅ Bot ready for new signals."


@app.route("/test_quote", methods=["GET"])
def test_quote():
    missing = [f for f in QUOTE_BG_FILES if not os.path.exists(os.path.join(QUOTE_BG_DIR, f))]
    send_daily_quote()
    if missing:
        return f"Test quote sent, but missing background files: {missing}. Check quote_bg folder on GitHub."
    return "Test quote sent! ✅ Check your channels."


@app.route("/", methods=["GET"])
def health():
    with state_lock:
        gold = active_trades.get("XAUUSD")
        btc  = active_trades.get("BTCUSD")
    ch2_info = f" | Channel 2: {CHAT_ID_2}" if CHAT_ID_2 else " | Channel 2: not set"
    bg_found = sum(1 for f in QUOTE_BG_FILES if os.path.exists(os.path.join(QUOTE_BG_DIR, f)))
    return (
        f"Kevin Gold Signals Bot is running! ✅\n"
        f"Channel 1: {CHAT_ID}{ch2_info}\n"
        f"Gold trade active: {'Yes' if gold else 'No'}\n"
        f"Bitcoin trade active: {'Yes' if btc else 'No'}\n"
        f"Price monitor: Running every 30s\n"
        f"State backups: 3 files\n"
        f"Quote backgrounds found: {bg_found}/10"
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=price_monitor, daemon=True).start()
    threading.Thread(target=quote_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
