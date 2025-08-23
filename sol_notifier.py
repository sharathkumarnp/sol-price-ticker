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
    # layout
    W, H = 1200, 628             # final image size
    CARD_MARGIN = 16             # inset so rounded edge is visible
    RADIUS = 42                  # corner radius
    LEFT_X = 90                  # left shift for price text
    PRICE_MAX_W = W - LEFT_X - 160

    # fonts (modern if available)
    FONT_BOLD = "Inter-Bold.ttf" if os.path.exists("Inter-Bold.ttf") else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_MED  = "Inter-Medium.ttf" if os.path.exists("Inter-Medium.ttf") else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # load banner
    banner_path = "sol-card.jpg" if os.path.exists("sol-card.jpg") else None
    if banner_path:
        bg = Image.open(banner_path).convert("RGBA")
    else:
        # fallback gradient
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        g = ImageDraw.Draw(bg)
        for y in range(H):
            r = int(14 + (90 - 14) * y / H)
            g_v = int(20 + (230 - 20) * y / H)
            b_v = int(30 + (210 - 30) * y / H)
            g.line([(0, y), (W, y)], fill=(r, g_v, b_v, 255))

    # resize and round
    card_w, card_h = W - 2 * CARD_MARGIN, H - 2 * CARD_MARGIN
    bg = bg.resize((card_w, card_h), Image.LANCZOS)
    mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card_w, card_h), RADIUS, fill=255)
    rounded_card = Image.new("RGBA", (card_w, card_h))
    rounded_card.paste(bg, (0, 0), mask)

    # solid canvas (no transparency -> Telegram won't add a white frame)
    CANVAS_BG = (12, 12, 12)  # near-black
    canvas = Image.new("RGB", (W, H), CANVAS_BG)
    canvas.paste(rounded_card.convert("RGB"), (CARD_MARGIN, CARD_MARGIN))

    # overlay text
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(overlay)

    price_str = f"${q2(price):,.2f}"

    # auto-size price
    font_big = _autosize_font(dr, price_str, PRICE_MAX_W, 160, FONT_BOLD)
    _, _, tw, th = dr.textbbox((0, 0), price_str, font=font_big)
    x = LEFT_X
    y = (H - th) // 2 - 8

    # subtle shadow + text
    dr.text((x + 3, y + 3), price_str, font=font_big, fill=(0, 0, 0, 120))
    dr.text((x, y), price_str, font=font_big, fill=(255, 255, 255, 255))

    # footer (optional: keep empty or add handle if you want)
    # handle = "@solpriceticker"
    # f_small = ImageFont.truetype(FONT_MED, 38) if os.path.exists(FONT_MED) else ImageFont.load_default()
    # _, _, hw, hh = dr.textbbox((0, 0), handle, font=f_small)
    # dr.text(((W - hw)//2, H - hh - 28), handle, font=f_small, fill=(235, 240, 255, 230))

    # compose and save JPEG (smaller/faster)
    final = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    final.save("sol_card.jpg", "JPEG", quality=90, optimize=True)

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
