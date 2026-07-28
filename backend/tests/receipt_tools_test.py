"""Test script for process_receipt_image tool on PostgreSQL."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, ReceiptExtraction
from tools.receipt_tools import process_receipt_image, ProcessReceiptImageInput
from tests.test_helpers import TEST_DATABASE_URL

engine = create_engine(TEST_DATABASE_URL, echo=False)


def run_tests():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    results = []

    def t(name, fn):
        try:
            fn()
            print(f"  PASS: {name}")
            results.append((name, True))
        except Exception as e:
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")
            results.append((name, False))

    def t1():
        s = Session()
        r = process_receipt_image(ProcessReceiptImageInput(
            image_data="iVBORw0KGgoAAAANSUhEUgAA...", image_filename="receipt.png"), s)
        assert r.status == "extracted_pending_approval"
        assert r.confidence > 0.6
        assert r.vendor_name is not None
        assert r.needs_approval == True
        s.close()

    def t2():
        s = Session()
        r = process_receipt_image(ProcessReceiptImageInput(
            image_data="NR:not-a-receipt-image-data", image_filename="photo.jpg"), s)
        assert r.confidence < 0.3
        assert r.status == "unrecognized_image"
        assert r.vendor_name is None
        s.close()

    def t3():
        s = Session()
        r = process_receipt_image(ProcessReceiptImageInput(
            image_data="BL:blurry-receipt-partial", image_filename="receipt.jpg"), s)
        assert 0.3 <= r.confidence <= 0.6
        assert r.status == "extracted_pending_approval"
        s.close()

    def t4():
        s = Session()
        try:
            process_receipt_image(ProcessReceiptImageInput(
                image_data="NG:negative-amount-receipt", image_filename="receipt.png"), s)
            assert False
        except ValueError as e:
            assert "Invalid receipt amount" in str(e)
        s.close()

    def t5():
        s = Session()
        try:
            process_receipt_image(ProcessReceiptImageInput(
                image_data="ZD:zero-amount-receipt", image_filename="receipt.png"), s)
            assert False
        except ValueError as e:
            assert "Invalid receipt amount" in str(e)
        s.close()

    def t6():
        s = Session()
        try:
            process_receipt_image(ProcessReceiptImageInput(
                image_data="text-data", image_filename="receipt.txt"), s)
            assert False
        except ValueError as e:
            assert "Unsupported image format" in str(e)
        s.close()

    t("Normal receipt extraction", t1)
    t("Non-receipt image -> confidence < 0.3", t2)
    t("Blurry/partial -> confidence 0.3-0.6", t3)
    t("Negative amount -> ValueError", t4)
    t("Zero amount -> ValueError", t5)
    t("Wrong format -> ValueError", t6)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results: print(f"  [{ok}] {name}")
    print(f"\nResults: {passed}/{total} passed\n")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
