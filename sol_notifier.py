import json, os, requests
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Precision config
getcontext().prec = 16

# --- Configuration ---
DELTA = Decimal(os.environ.get("DELTA", "0.01"))  # Alert when price changes by $5
STATE_FILE = "state.json"
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Price formatting
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
    from PIL import ImageFont, Image

    # Load background image
    bg = Image.open("sol-card.jpg").convert("RGBA")

    # Resize banner to card size
    w, h = 1200, 628
    bg = bg.resize((w, h))

    # Rounded mask
    radius = 40
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (w, h)], radius=radius, fill=255)
    bg.putalpha(mask)

    # Fonts
    font_bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_reg_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_big = ImageFont.truetype(font_bold_path, 160) if os.path.exists(font_bold_path) else ImageFont.load_default()
    font_small = ImageFont.truetype(font_reg_path, 48) if os.path.exists(font_reg_path) else ImageFont.load_default()

    # Overlay
    overlay = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Price text (slightly left of center)
    price_str = f"${price:,.2f}"
    tw, th = draw.textbbox((0, 0), price_str, font=font_big)[2:]
    x_offset = (w - tw) // 2 - 150   # shift left by 150px
    draw.text((x_offset, (h - th) // 2 - 20), price_str, fill=(255, 255, 255, 255), font=font_big)

    # Footer handle (slightly below)
    footer = "@solpriceticker"
    ftw, fth = draw.textbbox((0, 0), footer, font=font_small)[2:]
    draw.text(((w - ftw) // 2, h - fth - 50), footer, fill=(220, 220, 255, 255), font=font_small)

    # Merge
    final = Image.alpha_composite(bg, overlay)
    final.save("sol_card.png", "PNG", optimize=True)


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

        # Pick emoji based on direction
        if delta > 0:
            emoji = "📈"
        elif delta < 0:
            emoji = "📉"
        else:
            emoji = "〰️"

        caption = f"{emoji} {pretty_price(price)} @solpriceticker"

        send_photo_to_telegram(caption)
        state["last_price"] = str(price)

        save_state(state)
        print(f"Posted change {delta:+.2f}, new last_price={price}")
    else:
        print(f"No alert: Δ={delta:+.2f}, threshold={DELTA:.2f}")

if __name__ == "__main__":
    main()
