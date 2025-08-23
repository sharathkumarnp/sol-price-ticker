import json, os, requests
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple

# -------- precision --------
getcontext().prec = 16

# -------- config --------
DELTA = Decimal(os.environ.get("DELTA", "0.01"))   # alert threshold (absolute dollars)
STATE_FILE = "state.json"
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# -------- helpers --------
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

def _autosize_font(draw, text: str, max_width: int, start: int, path: str):
    """Decrease font size until text fits within max_width."""
    size = start
    while size > 10:
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()
        w, _ = draw.textbbox((0, 0), text, font=f)[2:]
        if w <= max_width:
            return f
        size -= 2
    return ImageFont.load_default()

# -------- card rendering --------
def make_card(price: Decimal, delta: Decimal):

    # ---- layout ----
    W, H = 1200, 628
    RADIUS = 42

    # ---- fonts ----
    FONT_BOLD = "Inter-Bold.ttf" if os.path.exists("Inter-Bold.ttf") else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    # ---- load fixed banner ----
    bg = Image.open("sol-card.png").convert("RGBA")
    bg = bg.resize((W, H), Image.LANCZOS)

    # ---- rounded mask ----
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W, H), RADIUS, fill=255)
    card = Image.new("RGBA", (W, H))
    card.paste(bg, (0, 0), mask)

    # ---- overlay for text ----
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    dr = ImageDraw.Draw(overlay)

    price_str = f"${q2(price):,.2f}"

    # autosize price text to fit width
    font_big = _autosize_font(dr, price_str, W - 200, 160, FONT_BOLD)

    _, _, tw, th = dr.textbbox((0, 0), price_str, font=font_big)
    x = (W - tw) // 2
    y = (H - th) // 2

    # draw price in pure black
    dr.text((x, y), price_str, font=font_big, fill=(0, 0, 0, 255))

    # ---- merge and save ----
    final = Image.alpha_composite(card, overlay).convert("RGB")
    final.save("sol_card.jpg", "JPEG", quality=95, optimize=True)


def send_photo_to_telegram(caption=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open("sol_card.jpg", "rb") as f:  # JPEG now
        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption or "", "parse_mode": "HTML"}
        files = {"photo": f}
        requests.post(url, data=data, files=files, timeout=30).raise_for_status()

# -------- main --------
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

        # caption emoji by direction
        emoji = "📈" if delta > 0 else ("📉" if delta < 0 else "〰️")
        caption = f"{emoji} {pretty_price(price)} @solpriceticker"

        send_photo_to_telegram(caption)
        state["last_price"] = str(price)
        save_state(state)
        print(f"Posted change {delta:+.2f}, new last_price={price}")
    else:
        print(f"No alert: Δ={delta:+.2f}, threshold={DELTA:.2f}")

if __name__ == "__main__":
    main()
