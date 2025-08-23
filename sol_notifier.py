import json, os, time, requests
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

# --- Config ---
SYMBOL = "SOLUSDT"  # Binance symbol
STEP = 10           # alert every $10 increase
STATE_FILE = "state.json"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"

def get_sol_price():
    r = requests.get(BINANCE_URL, params={"symbol": SYMBOL}, timeout=15)
    r.raise_for_status()
    return float(r.json()["price"])

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

def floor_to_step(v, step):
    return int(v // step) * step

def make_card(price):
    # Simple 1200x628 card with gradient + big price text (PNG)
    w, h = 1200, 628
    img = Image.new("RGB", (w, h), (42, 0, 82))

    # gradient
    for y in range(h):
        ratio = y / h
        r = int(120 + 60*ratio)
        g = int(50 + 40*ratio)
        b = int(180 + 50*ratio)
        ImageDraw.Draw(img).line([(0,y),(w,y)], fill=(r,g,b))

    draw = ImageDraw.Draw(img)

    # try to use a default font; Pillow will pick something available
    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") else ImageFont.load_default()
    font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 46) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ImageFont.load_default()

    # header
    draw.text((60, 50), "SOL / USDT", fill=(230, 230, 255), font=font_med)

    # big price
    price_text = f"${price:,.2f}"
    tw, th = draw.textbbox((0,0), price_text, font=font_big)[2:]
    draw.text(((w - tw)//2, (h - th)//2 - 40), price_text, fill=(255,255,255), font=font_big)

    # footer (timestamp)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    footer = f"Auto Update • {now}"
    ftw, fth = draw.textbbox((0,0), footer, font=font_med)[2:]
    draw.text(((w - ftw)//2, h - fth - 50), footer, fill=(220,220,240), font=font_med)

    # diagonal mini-arrow (stylized)
    draw.line([(80,140),(200,80)], fill=(245,245,255), width=10)
    draw.polygon([(200,80),(180,78),(192,92)], fill=(245,245,255))

    img.save("sol_card.png", "PNG")

def send_photo_to_telegram(caption=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open("sol_card.png", "rb") as f:
        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption or "", "parse_mode": "HTML"}
        files = {"photo": f}
        requests.post(url, data=data, files=files, timeout=30).raise_for_status()

def main():
    state = load_state()
    last_step = state.get("last_step")  # last $10 level we notified
    price = get_sol_price()
    current_step = floor_to_step(price, STEP)

    if last_step is None:
        # First run → initialize, no post
        state["last_step"] = current_step
        save_state(state)
        print(f"Initialized at {price} (bucket {current_step})")
        return

    if current_step > last_step:
        make_card(price)
        caption = f"📈 <b>SOL</b> crossed <b>${current_step}</b>\nCurrent: <b>${price:,.2f}</b>"
        send_photo_to_telegram(caption)
        state["last_step"] = current_step
        save_state(state)
        print(f"Posted new level {current_step}")
    else:
        print(f"No new higher $10 level yet (last={last_step}, now={current_step}, price={price})")

if __name__ == "__main__":
    main()
