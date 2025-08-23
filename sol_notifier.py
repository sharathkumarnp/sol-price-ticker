import json, os, requests
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from PIL import Image, ImageDraw, ImageFont

# Precision for financial math
getcontext().prec = 16

DELTA = Decimal(os.environ.get("DELTA", "0.01"))  # default alert threshold
STATE_FILE = "state.json"
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def get_sol_price() -> Decimal:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "solana", "vs_currencies": "usd"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return Decimal(r.json()["solana"]["usd"])

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

def pretty_price(d: Decimal) -> str:
    return f"${q2(d):,.2f}"

def make_card(price: Decimal, delta: Decimal):
    w, h = 1200, 628
    img = Image.new("RGB", (w, h), (28, 18, 64))
    dr = ImageDraw.Draw(img)
    for y in range(h):
        r, g, b = int(40 + y/h*30), int(30 + y/h*40), int(100 + y/h*80)
        dr.line([(0, y), (w, y)], fill=(r, g, b))

    font_path_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_path_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_big = ImageFont.truetype(font_path_bold, 150) if os.path.exists(font_path_bold) else ImageFont.load_default()
    font_med = ImageFont.truetype(font_path_reg, 46) if os.path.exists(font_path_reg) else ImageFont.load_default()

    dr.text((60, 50), "SOL / USDT", fill=(230, 230, 255), font=font_med)

    price_text = pretty_price(price)
    tw, th, _, _ = dr.textbbox((0,0), price_text, font=font_big)
    dr.text(((w - tw)//2, (h - th)//2 - 40), price_text, fill=(255,255,255), font=font_big)

    up = delta > 0
    dir_emoji = "📈" if up else ("📉" if delta < 0 else "〰️")
    delta_text = f"{dir_emoji} {delta:+.2f} since last alert"
    dtw, dth, _, _ = dr.textbbox((0,0), delta_text, font=font_med)
    dr.text(((w - dtw)//2, (h - dth)//2 + 100), delta_text, fill=(220, 235, 255), font=font_med)

    if up:
        dr.line([(80, 140), (220, 80)], fill=(255, 255, 255), width=10)
        dr.polygon([(220, 80), (200, 78), (212, 92)], fill=(255, 255, 255))
    else:
        dr.line([(80, 80), (220, 140)], fill=(255, 255, 255), width=10)
        dr.polygon([(220, 140), (200, 138), (212, 152)], fill=(255, 255, 255))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    footer = f"Auto Update • {now}"
    ftw, fth, _, _ = dr.textbbox((0,0), footer, font=font_med)
    dr.text(((w - ftw)//2, h - fth - 50), footer, fill=(220,220,240), font=font_med)

    img.save("sol_card.png", "PNG")

def send_photo_to_telegram(caption=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open("sol_card.png", "rb") as f:
        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption or "", "parse_mode": "HTML"}
        files = {"photo": f}
        requests.post(url, data=data, files=files, timeout=30).raise_for_status()

def main():
    state = load_state()
    last_str = state.get("last_price")
    price = q2(get_sol_price())

    if last_str is None:
        state["last_price"] = str(price)
        save_state(state)
        print(f"Initialized at {price}")
        return

    last = q2(Decimal(last_str))
    delta = price - last

    if abs(delta) >= DELTA:
        make_card(price, delta)
        caption = f"<b>SOL</b> moved {delta:+.2f} since last alert\nCurrent: <b>{pretty_price(price)}</b>"
        send_photo_to_telegram(caption)
        state["last_price"] = str(price)
        save_state(state)
        print(f"Posted change {delta:+.2f}, new last_price={price}")
    else:
        print(f"No alert: |Δ|={abs(delta):.2f} < {DELTA:.2f} (last={last}, now={price})")

if __name__ == "__main__":
    main()
