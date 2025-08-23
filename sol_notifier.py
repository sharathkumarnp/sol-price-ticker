import json, os, requests
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from PIL import Image, ImageDraw, ImageFont, ImageOps
from typing import Tuple


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

def _autosize_font(draw, text: str, max_width: int, start: int, path: str) -> "ImageFont.FreeTypeFont":

    """Decrease font size until text fits within max_width."""
    size = start
    while size > 10:
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            f = ImageFont.load_default()
            return f
        w, _ = draw.textbbox((0, 0), text, font=f)[2:]
        if w <= max_width:
            return f
        size -= 2
    return ImageFont.load_default()

def make_card(price: Decimal, delta: Decimal):

    from PIL import Image, ImageDraw, ImageFont

    # ---------- layout ----------
    W, H        = 1200, 628        # final card size
    RADIUS      = 48               # corner roundness
    PADDING     = 36               # inner transparent margin to avoid double-rounding artifacts
    LEFT_X      = 120              # left shift for price text
    PRICE_MAX_W = W - LEFT_X - 120 # keep some right breathing room

    # ---------- fonts (place optional TTFs in repo root for nicer look) ----------
    # Recommended to add these files to the repo for a modern look:
    #  - Inter-Bold.ttf   (or Manrope-ExtraBold.ttf)
    #  - Inter-Medium.ttf (or Manrope-SemiBold.ttf)
    FONT_BOLD = "Inter-Bold.ttf"    if os.path.exists("Inter-Bold.ttf")    else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_MED  = "Inter-Medium.ttf"  if os.path.exists("Inter-Medium.ttf")  else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # ---------- background (banner) with perfect rounded corners & transparency ----------
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))                  # transparent canvas
    try:
        bg = Image.open("sol-card.jpg").convert("RGBA")
    except Exception:
        # fallback to a soft gradient if banner missing
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gr = ImageDraw.Draw(bg)
        for y in range(H):
            r = int(14 + (90 - 14) * y / H)
            g = int(20 + (230 - 20) * y / H)
            b = int(30 + (210 - 30) * y / H)
            gr.line([(0, y), (W, y)], fill=(r, g, b, 255))
    bg = bg.resize((W - 2*PADDING, H - 2*PADDING), Image.LANCZOS)

    # mask for rounded rect
    mask = Image.new("L", (W - 2*PADDING, H - 2*PADDING), 0)
    md   = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, W - 2*PADDING, H - 2*PADDING], radius=RADIUS, fill=255)

    # paste rounded banner onto transparent base with inner padding
    base.paste(bg, (PADDING, PADDING), mask)

    # ---------- text overlay ----------
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    dr = ImageDraw.Draw(overlay)

    price_str = f"${q2(price):,.2f}"

    # auto-size big price to fit the available width
    tmp_font_for_measure = ImageFont.truetype(FONT_BOLD, 160) if os.path.exists(FONT_BOLD) else ImageFont.load_default()
    font_big = _autosize_font(dr, price_str, PRICE_MAX_W, 160, FONT_BOLD)

    # vertical placement around middle
    _, _, tw, th = dr.textbbox((0, 0), price_str, font=font_big)
    x = LEFT_X
    y = (H - th) // 2 - 10

    # subtle shadow for contrast
    shadow_offset = 3
    dr.text((x + shadow_offset, y + shadow_offset), price_str, font=font_big, fill=(0, 0, 0, 120))
    dr.text((x, y), price_str, font=font_big, fill=(255, 255, 255, 255))

    # small handle at bottom center (cleaner font & size)
    handle = ""
    font_small = ImageFont.truetype(FONT_MED, 40) if os.path.exists(FONT_MED) else ImageFont.load_default()
    _, _, hw, hh = dr.textbbox((0, 0), handle, font=font_small)
    dr.text(((W - hw) // 2, H - hh - 34), handle, font=font_small, fill=(235, 240, 255, 230))

    # merge and save (PNG with alpha for perfect corners)
    final = Image.alpha_composite(base, overlay)
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
