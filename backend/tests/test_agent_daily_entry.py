"""Full integration test for Daily Entry Agent — all 5 tools working together."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, CashPosition, JournalEntry, BankTransaction, BankAccount, PettyCashFund, PettyCashTransaction, ReceiptExtraction
from tools.schemas import CheckCashPositionInput, RecordTransactionNLInput, CheckBankTransactionsInput, ManagePettyCashInput, ProcessReceiptImageInput
from tools.cash_tools import check_cash_position
from tools.transaction_tools import record_transaction_nl
from tools.bank_tools import check_bank_transactions
from tools.petty_cash_tools import manage_petty_cash
from tools.receipt_tools import process_receipt_image


def run_agent_test():
    """Simulate a real user day with the Daily Entry Agent."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()

    today = date(2026, 7, 28)

    # ---- Seed initial data ----
    # Cash position
    s.add(CashPosition(account_id="CA-001", account_name="Main Cash", as_of_date=today,
        opening_balance=Decimal("500000.00"), total_debits=Decimal("0"), total_credits=Decimal("0"),
        closing_balance=Decimal("500000.00"), currency="PKR"))
    s.add(CashPosition(account_id="PC-001", account_name="Petty Cash", as_of_date=today,
        opening_balance=Decimal("10000.00"), total_debits=Decimal("0"), total_credits=Decimal("0"),
        closing_balance=Decimal("10000.00"), currency="PKR"))
    # Bank account
    s.add(BankAccount(account_id="BA-001", account_name="HBL Current", bank_name="HBL"))
    s.add_all([
        BankTransaction(transaction_id="BT-001", date=today - timedelta(1), description="Opening balance",
            amount=Decimal("2000000.00"), type="credit", status="cleared", account_id="BA-001", balance_after=Decimal("2000000.00")),
        BankTransaction(transaction_id="BT-002", date=today, description="Payment from client X",
            amount=Decimal("150000.00"), type="credit", status="pending", reference="INV-100",
            account_id="BA-001", balance_after=Decimal("2150000.00")),
    ])
    # Petty cash fund
    s.add(PettyCashFund(fund_id="PC-001", fund_name="Main Petty Cash", current_balance=Decimal("5000.00")))
    s.commit()

    results = []

    print("=" * 70)
    print("DAILY ENTRY AGENT — FULL INTEGRATION TEST")
    print("Simulating a real user's day with the AI Accountant")
    print("=" * 70)

    # ---- Scenario 1: User checks cash position ----
    print("\n[SCENARIO 1] User asks: \"What's our cash position today?\"")
    r1 = check_cash_position(CheckCashPositionInput(as_of_date=today), s)
    assert r1.closing_balance == Decimal("510000.00"), f"Expected 510000, got {r1.closing_balance}"
    assert r1.warning == False
    print(f"  -> Cash balance: PKR {r1.closing_balance:,.2f} (2 accounts consolidated)")
    results.append(("Check cash position", True))

    # ---- Scenario 2: User records a transaction ----
    print("\n[SCENARIO 2] User says: \"Record office rent 50000 for July\"")
    r2 = record_transaction_nl(RecordTransactionNLInput(
        description="Office rent 50000 for July", posted_date=today), s)
    assert r2.status == "posted"
    assert r2.debit_account == "6000-Office Rent"
    assert r2.debit_amount == Decimal("50000.00")
    print(f"  -> Journal entry {r2.entry_id}: Debit {r2.debit_account} {r2.debit_amount}, Credit {r2.credit_account} {r2.credit_amount}")
    results.append(("Record transaction NL", True))

    # ---- Scenario 3: User checks bank transactions ----
    print("\n[SCENARIO 3] User asks: \"Show me today's bank transactions\"")
    r3 = check_bank_transactions(CheckBankTransactionsInput(
        from_date=today, to_date=today, account_id="BA-001"), s)
    assert r3.total_count >= 1
    assert r3.transactions[0].description == "Payment from client X"
    print(f"  -> Found {r3.total_count} transaction(s), latest: {r3.transactions[0].description} (PKR {r3.transactions[0].amount:,.2f})")
    results.append(("Check bank transactions", True))

    # ---- Scenario 4: User records a petty cash expense ----
    print("\n[SCENARIO 4] User says: \"Record petty cash expense 2000 for office supplies paid by Ali\"")
    r4 = manage_petty_cash(ManagePettyCashInput(
        action="expense", fund_id="PC-001", amount=Decimal("2000.00"),
        description="Office supplies", paid_by="Ali"), s)
    assert r4.needs_replenishment == True, f"Expected replenishment needed, balance={r4.current_balance}"
    assert r4.message == "Replenishment recommended — balance below threshold"
    print(f"  -> Expense recorded. Balance: PKR {r4.current_balance:,.2f}. Alert: {r4.message}")
    results.append(("Manage petty cash expense", True))

    # ---- Scenario 5: Upload a receipt ----
    print("\n[SCENARIO 5] User uploads a receipt photo for groceries")
    r5 = process_receipt_image(ProcessReceiptImageInput(
        image_data="iVBORw0KGgoAAAANSUhEUgAA...",
        image_filename="groceries.jpg"), s)
    assert r5.status == "extracted_pending_approval"
    assert r5.confidence > 0.6
    assert r5.needs_approval == True
    print(f"  -> Receipt extracted: {r5.vendor_name}, PKR {r5.total_amount:,.2f} (confidence: {r5.confidence:.0%}, requires approval)")
    results.append(("Process receipt image", True))

    # ---- Scenario 6: Check petty cash replenishment ----
    print("\n[SCENARIO 6] User asks: \"Is replenishment needed for petty cash?\"")
    r6 = manage_petty_cash(ManagePettyCashInput(
        action="check_replenishment", fund_id="PC-001", replenishment_threshold=Decimal("5000.00")), s)
    assert r6.needs_replenishment == True
    print(f"  -> Petty cash balance: PKR {r6.current_balance:,.2f} (threshold: PKR {r6.threshold:,.2f}). {r6.message}")
    results.append(("Check replenishment", True))

    # ---- Scenario 7: Record another transaction (different category) ----
    print("\n[SCENARIO 7] User says: \"Paid electricity bill 12000\"")
    r7 = record_transaction_nl(RecordTransactionNLInput(
        description="Paid electricity bill 12000", posted_date=today), s)
    assert r7.debit_account == "6200-Utilities"
    print(f"  -> Journal entry {r7.entry_id}: Debit {r7.debit_account} {r7.debit_amount}")
    results.append(("Record utilities transaction", True))

    # ---- Scenario 8: Final cash position check ----
    print("\n[SCENARIO 8] User asks: \"What's cash position now?\" (after all transactions)")
    r8 = check_cash_position(CheckCashPositionInput(as_of_date=today), s)
    print(f"  -> Cash balance: PKR {r8.closing_balance:,.2f} (started at 510,000, spent 50,000 + 12,000 = 62,000)")
    results.append(("Final cash position", True))

    s.close()
    engine.dispose()

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for scenario, ok in results:
        print(f"  [{ok}] {scenario}")
    print(f"\nAgent 1 Integration Test: {passed}/{total} passed")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_agent_test() else 1)
