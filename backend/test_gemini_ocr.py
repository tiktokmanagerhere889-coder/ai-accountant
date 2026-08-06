"""Test Gemini vision for receipt OCR — generate a receipt, send to Gemini, parse JSON.

Uses the SAME OpenAI-compat endpoint as the app (create_gemini_provider).
Run: cd backend && python test_gemini_ocr.py
"""
import sys, os, json, base64, io
sys.path.insert(0, os.getcwd())
from PIL import Image, ImageDraw, ImageFont

def make_receipt() -> bytes:
    """Draw a realistic grocery receipt PNG."""
    W, H = 380, 520
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        small = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
        small = font
    y = 10
    lines = [
        ("AL-MADINA GENERAL STORE", font),
        ("Shop #42, Main Bazaar, Lahore", small),
        ("Tel: 0300-1234567", small),
        ("--------------------------------", small),
        ("TOTAL TODAY: 2 ITEMS", small),
        ("--------------------------------", small),
        ("Sugar 1kg            Rs 195.00", small),
        ("Milk 1L             Rs 220.00", small),
        ("--------------------------------", small),
        ("SUBTOTAL            Rs 415.00", small),
        ("GST (16%)           Rs  66.40", small),
        ("TOTAL               Rs 481.40", small),
        ("--------------------------------", small),
        ("Cash Received       Rs 500.00", small),
        ("Change              Rs  18.60", small),
        ("--------------------------------", small),
        ("Date: 05/08/2026  Time: 14:32", small),
        ("Cashier: Ali  Thank you!", small),
    ]
    for text, f in lines:
        d.text((12, y), text, fill="black", font=f)
        y += 24
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()

def main():
    png = make_receipt()
    b64 = base64.b64encode(png).decode()
    print(f"receipt PNG: {len(png)} bytes, base64 {len(b64)} chars")

    from agent_defs.model_providers import create_gemini_provider, get_api_key
    from openai import OpenAI
    api_key = get_api_key("GEMINI_API_KEY")
    print(f"gemini key present: {bool(api_key)}")

    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=45.0,
    )
    prompt = (
        "Extract receipt data from this image. Return ONLY a JSON object with keys: "
        "vendor_name (string), total_amount (number), date (string YYYY-MM-DD), "
        "currency (string). No markdown, no extra text. If a field is unclear use null."
    )
    resp = client.chat.completions.create(
        model="gemini-flash-lite-latest",
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
        max_tokens=300,
    )
    text = resp.choices[0].message.content.strip()
    print("RAW RESPONSE:", text[:300])
    # Try to parse JSON (may be wrapped in ```json)
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        print("\nPARSED:", json.dumps(data, indent=2))
        ok = (
            "Al-Madina" in str(data.get("vendor_name", "")).lower()
            and abs(float(data.get("total_amount", 0)) - 481.40) < 1.0
        )
        print("\nEXTRACTION OK:", ok)
    except Exception as e:
        print("JSON parse failed:", e)

if __name__ == "__main__":
    main()
