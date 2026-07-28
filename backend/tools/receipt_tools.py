from __future__ import annotations

import base64
import re
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


def _simulate_llm_extraction(image_data: str) -> dict:
    """Simulate Cerebras/Groq LLM vision extraction.

    Deterministic based on image_data prefix for testing:
    - 'NR:' prefix → non-receipt image
    - 'BL:' prefix → blurry/partial receipt
    - 'NG:' prefix → negative amount (edge case)
    - 'ZD:' prefix → zero amount (edge case)
    - otherwise → normal receipt extraction
    """
    if image_data.startswith("NR:"):
        return {
            "vendor_name": None,
            "total_amount": Decimal("0"),
            "date": None,
            "confidence": Decimal("0.10"),
        }
    if image_data.startswith("BL:"):
        return {
            "vendor_name": "Uncertain Vendor",
            "total_amount": Decimal("1500.00"),
            "date": date.today(),
            "confidence": Decimal("0.45"),
        }
    if image_data.startswith("NG:"):
        return {
            "vendor_name": "Test Store",
            "total_amount": Decimal("-500.00"),
            "date": date.today(),
            "confidence": Decimal("0.90"),
        }
    if image_data.startswith("ZD:"):
        return {
            "vendor_name": "Test Store",
            "total_amount": Decimal("0.00"),
            "date": date.today(),
            "confidence": Decimal("0.90"),
        }
    # Normal receipt
    return {
        "vendor_name": "Abdullah Super Market",
        "total_amount": Decimal("3500.00"),
        "date": date.today(),
        "confidence": Decimal("0.92"),
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

    Validates the image format, simulates LLM vision extraction, validates the
    extracted amount, determines the extraction status based on confidence, and
    persists the result to the receipt_extractions table.

    Args:
        input: Pydantic model with image_data (base64), image_filename, and optional suggested_account.
        db: SQLAlchemy Session for database operations.

    Returns:
        ProcessReceiptImageOutput with extraction results.

    Raises:
        ValueError: If image format/size is unsupported or amount is invalid (zero/negative).
    """
    # Step 1: Validate image format and size (edge case 4)
    _validate_image_format(input.image_data, input.image_filename)

    # Step 2: Simulate LLM vision extraction
    extraction = _simulate_llm_extraction(input.image_data)

    # Step 3: Determine confidence first
    confidence = extraction["confidence"]
    confidence_float = float(confidence)

    # Edge case 1: Non-receipt image — skip amount validation
    if confidence_float < 0.3:
        status = "unrecognized_image"
        vendor_name = None
        total_amount = Decimal("0.00")
    else:
        # Edge case 3: Validate amount > 0 for actual receipts
        total_amount = extraction["total_amount"]
        if total_amount <= Decimal("0"):
            raise ValueError("Invalid receipt amount")

        # Edge case 2: Blurry/partial — still valid, just lower confidence
        status = "extracted_pending_approval"
        vendor_name = extraction["vendor_name"]

    # Step 5: Generate extraction ID
    extraction_id = _generate_extraction_id(db)

    # Step 6: Persist to DB
    receipt_extraction = ReceiptExtraction(
        extraction_id=extraction_id,
        vendor_name=vendor_name,
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

    # Step 7: Return structured output
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
