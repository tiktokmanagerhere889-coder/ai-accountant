"""End-to-end test: process_receipt_image via Gemini vision (no Document AI).

Reuses the same receipt PNG generator as test_gemini_ocr.py and calls the real
tool function (validation -> Gemini extraction -> DB persist -> output model).

Run: cd backend && python test_receipt_gemini.py
"""
import sys, os, base64, io
sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw, ImageFont

from tools.receipt_tools import process_receipt_image, ProcessReceiptImageInput
from db.database import SessionLocal


def make_receipt() -> bytes:
    """Draw a realistic grocery receipt PNG (same as test_gemini_ocr.py)."""
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

    db = SessionLocal()
    try:
        out = process_receipt_image(
            ProcessReceiptImageInput(image_data=b64, image_filename="receipt.png"),
            db,
        )
    finally:
        db.close()

    print("\n=== RESULT ===")
    print("extraction_id:", out.extraction_id)
    print("vendor_name:  ", out.vendor_name)
    print("total_amount: ", out.total_amount)
    print("date:         ", out.date)
    print("currency:     ", out.currency)
    print("confidence:   ", out.confidence)
    print("status:       ", out.status)

    ok = (
        out.total_amount is not None
        and abs(float(out.total_amount) - 481.40) < 1.0
        and out.vendor_name
    )
    print("\nTOOL PASS:", ok)


if __name__ == "__main__":
    main()
