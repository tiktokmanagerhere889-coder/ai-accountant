from __future__ import annotations

import base64
import os
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


def _get_document_ai_client():
    """Create and return a Document AI client using service account credentials."""
    from google.cloud import documentai

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path or not os.path.exists(credentials_path):
        raise ValueError(
            "GOOGLE_APPLICATION_CREDENTIALS not set or file not found. "
            "Set GOOGLE_APPLICATION_CREDENTIALS to the path of your service account JSON."
        )

    client = documentai.DocumentProcessorServiceClient()
    return client


def _get_processor_name() -> str:
    """Get the full processor resource name from environment variables."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    location = os.environ.get("GOOGLE_DOCUMENT_AI_LOCATION", "us")
    processor_id = os.environ.get("GOOGLE_DOCUMENT_AI_PROCESSOR_ID")

    if not all([project_id, location, processor_id]):
        raise ValueError(
            "Missing Document AI configuration. Set GOOGLE_CLOUD_PROJECT_ID, "
            "GOOGLE_DOCUMENT_AI_LOCATION, and GOOGLE_DOCUMENT_AI_PROCESSOR_ID."
        )

    return f"projects/{project_id}/locations/{location}/processors/{processor_id}"


def _extract_receipt_data(image_data: str, image_filename: str) -> dict:
    """
    Process a receipt image through Google Document AI Receipt Parser.

    Returns dict with: vendor_name, total_amount, date, confidence
    """
    # Decode base64 image
    image_bytes = base64.b64decode(image_data)

    # Determine MIME type from filename
    ext = image_filename.rsplit(".", 1)[-1].lower() if "." in image_filename else ""
    mime_type = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(ext, "image/jpeg")

    # Get Document AI client and processor
    client = _get_document_ai_client()
    processor_name = _get_processor_name()

    # Prepare the request
    from google.cloud import documentai
    raw_document = documentai.RawDocument(content=image_data, mime_type="image/jpeg")

    # Determine MIME type from filename for the raw document
    ext = image_filename.rsplit(".", 1)[-1].lower() if "." in image_filename else ""
    mime_type = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(ext, "image/jpeg")

    # Decode base64 to raw bytes
    image_bytes = base64.b64decode(image_data)
    raw_document = documentai.RawDocument(content=image_bytes, mime_type=mime_type)

    from google.cloud import documentai_v1
    request = documentai_v1.ProcessRequest(name=_get_processor_name(), raw_document=raw_document)

    # Process the document
    result = client.process_document(request=request)
    document = result.document

    # Parse the extracted entities
    vendor_name = None
    total_amount = None
    receipt_date = None
    confidence = 0.0

    # Parse entities from the receipt parser
    for entity in document.entities:
        entity_type = entity.type_.lower() if entity.type_ else ""
        mention_text = entity.mention_text.strip() if entity.mention_text else ""
        confidence = max(confidence, entity.confidence if entity.confidence else 0.0)

        if entity_type in ("supplier_name", "vendor_name", "merchant_name", "receiver_name"):
            vendor_name = mention_text
        elif entity_type in ("total_amount", "net_amount", "amount", "total"):
            # Parse amount, handle currency symbols
            amount_str = re.sub(r"[^\d.,]", "", mention_text)
            amount_str = amount_str.replace(",", "")
            try:
                total_amount = Decimal(amount_str) if amount_str else None
            except Exception:
                total_amount = None
        elif entity_type in ("date", "receipt_date", "transaction_date"):
            # Try to parse date
            try:
                receipt_date = datetime.strptime(mention_text, "%Y-%m-%d").date()
            except Exception:
                # Try other common formats
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y"):
                    try:
                        receipt_date = datetime.strptime(mention_text, fmt).date()
                        break
                    except Exception:
                        continue

    # Default confidence if none found
    if confidence == 0.0:
        confidence = 0.85

    return {
        "vendor_name": vendor_name,
        "total_amount": total_amount,
        "date": receipt_date,
        "confidence": Decimal(str(confidence)),
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

    Validates the image format, extracts data via Google Document AI,
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

    # Step 2: Extract receipt data via Google Document AI
    try:
        extraction = _extract_receipt_data(input.image_data, input.image_filename)
    except Exception as e:
        raise ValueError(f"Document AI extraction failed: {str(e)}")

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