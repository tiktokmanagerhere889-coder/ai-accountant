"""Tests for Tool 7 (categorize_fixed_asset) and Tool 8 (manage_contact)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, FixedAsset, Contact
from tools.schemas import CategorizeFixedAssetInput, ManageContactInput
from tools.asset_tools import categorize_fixed_asset
from tools.contact_tools import manage_contact

from tests.test_helpers import TEST_DATABASE_URL

engine = create_engine(TEST_DATABASE_URL, echo=False)
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)


def run_tests():
    results = []

    def t(name, fn):
        try:
            fn()
            print("  PASS: {}".format(name))
            results.append((name, True))
        except Exception as e:
            print("  FAIL: {} — {}: {}".format(name, type(e).__name__, e))
            results.append((name, False))

    # ------------------------------------------------------------------ #
    #  Tool 7: categorize_fixed_asset                                    #
    # ------------------------------------------------------------------ #

    def t1():
        """Building/Property: useful_life=40, straight_line, residual=10%"""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Office Building",
            purchase_cost=Decimal("5000000.00"),
            purchase_date=date(2026, 1, 15),
        ), s)
        assert r.asset_name == "Office Building"
        assert r.suggested_useful_life == 40
        assert r.suggested_depreciation_method == "straight_line"
        assert r.suggested_residual_value == Decimal("500000.00")
        assert r.needs_approval is True
        assert r.status == "pending_approval"
        assert r.asset_id.startswith("FA-")
        db_asset = s.query(FixedAsset).filter_by(asset_id=r.asset_id).first()
        assert db_asset is not None
        assert db_asset.status == "pending_approval"
        s.close()

    def t2():
        """Vehicle: useful_life=10, declining_balance, residual=10%"""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Company Vehicle - Toyota",
            purchase_cost=Decimal("2500000.00"),
            purchase_date=date(2026, 3, 10),
        ), s)
        assert r.suggested_useful_life == 10
        assert r.suggested_depreciation_method == "declining_balance"
        assert r.suggested_residual_value == Decimal("250000.00")
        s.close()

    def t3():
        """Computer/IT: useful_life=5, straight_line, residual=5%"""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Dell Server",
            purchase_cost=Decimal("300000.00"),
            purchase_date=date(2026, 5, 20),
        ), s)
        assert r.suggested_useful_life == 5
        assert r.suggested_depreciation_method == "straight_line"
        assert r.suggested_residual_value == Decimal("15000.00")
        s.close()

    def t4():
        """Furniture: useful_life=10, straight_line, residual=10%"""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Office Furniture Desk Set",
            purchase_cost=Decimal("80000.00"),
            purchase_date=date(2026, 4, 1),
        ), s)
        assert r.suggested_useful_life == 10
        assert r.suggested_depreciation_method == "straight_line"
        assert r.suggested_residual_value == Decimal("8000.00")
        s.close()

    def t5():
        """Machinery: useful_life=15, declining_balance, residual=10%"""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="CNC Machinery Equipment",
            purchase_cost=Decimal("1500000.00"),
            purchase_date=date(2026, 2, 1),
        ), s)
        assert r.suggested_useful_life == 15
        assert r.suggested_depreciation_method == "declining_balance"
        assert r.suggested_residual_value == Decimal("150000.00")
        s.close()

    def t6():
        """Other (no keyword match): useful_life=5, straight_line, residual=5%"""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Goodwill Patent",
            purchase_cost=Decimal("500000.00"),
            purchase_date=date(2026, 6, 15),
        ), s)
        assert r.suggested_useful_life == 5
        assert r.suggested_depreciation_method == "straight_line"
        assert r.suggested_residual_value == Decimal("25000.00")
        s.close()

    def t7():
        """Explicit category override — asset_name doesn't match, category does."""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Custom Equipment",
            asset_category="Vehicle",
            purchase_cost=Decimal("1000000.00"),
            purchase_date=date(2026, 7, 1),
        ), s)
        assert r.suggested_useful_life == 10
        assert r.suggested_depreciation_method == "declining_balance"
        s.close()

    def t8():
        """Edge: non-matching asset_category name uses default config (5yr, straight_line, 5% residual)."""
        s = Session()
        r = categorize_fixed_asset(CategorizeFixedAssetInput(
            asset_name="Custom Software License",
            asset_category="Software",
            purchase_cost=Decimal("500000.00"),
            purchase_date=date(2026, 7, 1),
        ), s)
        # Non-matching category name should fall back to DEFAULT (Other)
        assert r.suggested_useful_life == 5
        assert r.suggested_depreciation_method == "straight_line"
        assert r.suggested_residual_value == Decimal("25000.00")  # 5% of 500000
        s.close()

    # ------------------------------------------------------------------ #
    #  Tool 8: manage_contact                                            #
    # ------------------------------------------------------------------ #

    def t9():
        """Add a new vendor contact."""
        s = Session()
        r = manage_contact(ManageContactInput(
            action="add",
            contact_type="vendor",
            contact_name="ABC Supplies",
            phone="+92-300-1234567",
            email="info@abcsupplies.com",
            address="123 Main Street, Karachi",
            tax_id="TAX-001-ABC",
        ), s)
        assert r.action_performed == "add"
        assert r.contact_name == "ABC Supplies"
        assert r.contact_type == "vendor"
        assert r.contact_id.startswith("CNT-")
        assert "created successfully" in r.message

        db_contact = s.query(Contact).filter_by(contact_id=r.contact_id).first()
        assert db_contact is not None
        assert db_contact.phone == "+92-300-1234567"
        assert db_contact.email == "info@abcsupplies.com"
        s.close()

    def t10():
        """Add a customer contact."""
        s = Session()
        r = manage_contact(ManageContactInput(
            action="add",
            contact_type="customer",
            contact_name="John Doe Retail",
            phone="+92-300-7654321",
            email="john@example.com",
        ), s)
        assert r.action_performed == "add"
        assert r.contact_name == "John Doe Retail"
        assert r.contact_type == "customer"
        s.close()

    def t11():
        """Duplicate detection — adding same name raises ValueError."""
        s = Session()
        try:
            manage_contact(ManageContactInput(
                action="add",
                contact_type="vendor",
                contact_name="ABC Supplies",
            ), s)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "already exists" in str(e).lower()
        s.close()

    def t12():
        """Update existing contact by name."""
        s = Session()
        r = manage_contact(ManageContactInput(
            action="update",
            contact_type="vendor",
            contact_name="ABC Supplies",
            phone="+92-300-9999999",
            email="new@abcsupplies.com",
        ), s)
        assert r.action_performed == "update"
        assert r.contact_type == "vendor"
        assert "updated successfully" in r.message

        db_contact = s.query(Contact).filter_by(contact_id=r.contact_id).first()
        assert db_contact.phone == "+92-300-9999999"
        assert db_contact.email == "new@abcsupplies.com"
        s.close()

    def t13():
        """Delete existing contact."""
        s = Session()
        # First add a contact to delete
        add_result = manage_contact(ManageContactInput(
            action="add",
            contact_type="vendor",
            contact_name="Temp Vendor",
        ), s)
        contact_id = add_result.contact_id

        r = manage_contact(ManageContactInput(
            action="delete",
            contact_type="vendor",
            contact_name="Temp Vendor",
        ), s)
        assert r.action_performed == "delete"
        assert "deleted successfully" in r.message

        db_contact = s.query(Contact).filter_by(contact_id=contact_id).first()
        assert db_contact is None
        s.close()

    def t14():
        """Delete non-existent contact raises ValueError."""
        s = Session()
        try:
            manage_contact(ManageContactInput(
                action="delete",
                contact_type="vendor",
                contact_name="NonExistent Ltd",
            ), s)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e).lower()
        s.close()

    def t15():
        """Search contacts by partial name."""
        s = Session()
        # Already have ABC Supplies in DB from earlier tests
        r = manage_contact(ManageContactInput(
            action="search",
            contact_type="vendor",
            contact_name="ABC",
        ), s)
        assert r.action_performed == "search"
        assert "Found" in r.message
        assert "ABC Supplies" in r.message
        s.close()

    def t16():
        """Search with no matches returns appropriate message."""
        s = Session()
        r = manage_contact(ManageContactInput(
            action="search",
            contact_type="vendor",
            contact_name="ZZZNonexistent",
        ), s)
        assert r.action_performed == "search"
        assert "No contacts found" in r.message
        s.close()

    # Register tests
    t("Building asset categorization", t1)
    t("Vehicle asset categorization", t2)
    t("Computer/IT asset categorization", t3)
    t("Furniture asset categorization", t4)
    t("Machinery asset categorization", t5)
    t("Other asset categorization (fallback)", t6)
    t("Explicit category override", t7)
    t("Non-matching category falls back to default config", t8)
    t("Add vendor contact", t9)
    t("Add customer contact", t10)
    t("Duplicate contact detection", t11)
    t("Update contact by name", t12)
    t("Delete contact", t13)
    t("Delete non-existent raises ValueError", t14)
    t("Search contacts by partial name", t15)
    t("Search with no matches", t16)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print("  [{}] {}".format(ok, name))
    print("\nResults: {}/{} passed\n".format(passed, total))
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
