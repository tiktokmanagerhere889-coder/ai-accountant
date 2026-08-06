from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.models import Base, ReceiptExtraction


class ProcessReceiptImageInput(BaseModel):
    image_data: str = Field(..., description="Base64-encoded receipt image")
    image_filename: str = Field(..., description="Original filename of the receipt image")
    suggested_account: str | None = Field(default=None, description="Optional account to post to (e.g., 'Office Rent')")


class ProcessReceiptImageOutput(BaseModel):
    extraction_id: str
    vendor_name: str | None
    total_amount: Decimal | None
    date: date | None
    currency: str = "PKR"
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score")
    needs_approval: bool = True
    status: str = "extracted_pending_approval"


_MAX_IMAGE_DATA_LENGTH = 13_333_333  # ~10MB in base64 chars (10MB * 4/3)
_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _validate_image_format(image_data: str, image_filename: str) -> None:
    """Validate image file extension and base64 data size."""
    ext = "." + image_filename.rsplit(".", 1)[-1].lower() if "." in image_filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported image format or size")
    if len(image_data) > _MAX_IMAGE_DATA_LENGTH:
        raise ValueError("Unsupported image format or size")


_GEMINI_RECEIPT_PROMPT = (
    "You are a receipt parser. Look at the receipt image and return ONLY a JSON "
    'object with exactly these keys: "vendor_name" (string or null), "total_amount" '
    '(number or null), "date" (string in YYYY-MM-DD format or null), "currency" '
    '(string or null). No markdown, no code fences, no extra text. If a field '
    "cannot be determined, use null. Example: "
    '{"vendor_name":"Al Madina Store","total_amount":481.40,"date":"2026-08-05","currency":"PKR"}'
)


def _extract_receipt_data(image_data: str, image_filename: str) -> dict:
    """
    Extract receipt fields using Gemini vision (OpenAI-compatible endpoint).

    Replaces Google Document AI, which required a Cloud project with billing
    enabled (403 without it). Gemini free tier does not need billing and shares
    the already-configured GEMINI_API_KEY + gemini-flash-lite-latest model.

    Returns dict with: vendor_name, total_amount, date, confidence
    """
    from openai import OpenAI
    from agent_defs.model_providers import get_api_key

    api_key = get_api_key("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Configure it to process receipts.")

    mime = "image/png" if image_filename.lower().endswith(".png") else "image/jpeg"
    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=45.0,
    )
    resp = client.chat.completions.create(
        model="gemini-flash-lite-latest",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _GEMINI_RECEIPT_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{image_data}",
                        },
                    },
                ],
            },
        ],
        max_tokens=200,
    )
    text = (resp.choices[0].message.content or "").strip()
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except Exception as e:
        raise ValueError(f"Gemini did not return valid JSON: {e}")

    vendor_name = data.get("vendor_name")
    total_amount = data.get("total_amount")
    raw_date = data.get("date")
    receipt_date = None
    if raw_date:
        raw_date = str(raw_date)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                receipt_date = datetime.strptime(raw_date, fmt).date()
                break
            except Exception:
                continue

    if total_amount is not None:
        total_amount = Decimal(str(total_amount))

    return {
        "vendor_name": vendor_name,
        "total_amount": total_amount,
        "date": receipt_date,
        "confidence": Decimal("0.85"),
    }


def _generate_extraction_id(db: Session) -> str:
    """Generate a unique extraction ID in REC-YYYYMMDD-NNN format."""
    today_str = date.today().strftime("%Y%m%d")
    existing = db.query(ReceiptExtraction).filter(
        ReceiptExtraction.extraction_id.like(f"REC-{today_str}-%")
    ).count()
    seq = existing + 1
    return f"REC-{today_str}-{seq:03d}"


def process_receipt_image(input: ProcessReceiptImageInput, db: Session) -> ProcessReceiptImageOutput:
    """Process a receipt image and return structured extraction results.

    Validates the image format, extracts data via Gemini vision,
    validates the extracted amount, determines the extraction status based on confidence,
    and persists the result to the receipt_extractions table.

    Args:
        input: Pydantic model with image_data (base64), image_filename, and optional suggested_account.
        db: SQLAlchemy Session for database operations.

    Returns:
        ProcessReceiptImageOutput with extraction results.

    Raises:
        ValueError: If image format/size is unsupported or amount is invalid (zero/negative).
    """
    # Step 1: Validate image format and size
    _validate_image_format(input.image_data, input.image_filename)

    # Step 2: Extract receipt data via Gemini vision
    try:
        extraction = _extract_receipt_data(input.image_data, input.image_filename)
    except Exception as e:
        raise ValueError(f"Receipt extraction failed: {str(e)}")

    # Step 3: Determine confidence first
    confidence = extraction["confidence"]
    confidence_float = float(confidence)

    # Edge case 1: Low confidence - treat as unrecognized
    if confidence_float < 0.3:
        status = "unrecognized_image"
        vendor_name = None
        total_amount = Decimal("0.00")
    else:
        # Edge case 3: Validate amount > 0 for actual receipts
        total_amount = extraction["total_amount"]
        if total_amount is None or total_amount <= Decimal("0"):
            raise ValueError("Invalid receipt amount")

        status = "extracted_pending_approval"
        vendor_name = extraction["vendor_name"]

    # Step 4: Generate extraction ID
    extraction_id = _generate_extraction_id(db)

    # Step 5: Persist to DB
    receipt_extraction = ReceiptExtraction(
        extraction_id=extraction_id,
        vendor_name=extraction.get("vendor_name"),
        total_amount=total_amount,
        date=extraction.get("date"),
        currency="PKR",
        confidence=confidence,
        needs_approval=1,
        status=status,
    )
    db.add(receipt_extraction)
    db.commit()
    db.refresh(receipt_extraction)

    # Step 6: Return structured output
    return ProcessReceiptImageOutput(
        extraction_id=receipt_extraction.extraction_id,
        vendor_name=receipt_extraction.vendor_name,
        total_amount=receipt_extraction.total_amount,
        date=receipt_extraction.date,
        currency=receipt_extraction.currency,
        confidence=float(receipt_extraction.confidence),
        needs_approval=True,
        status=receipt_extraction.status,
    )