"""Full integration test for Daily Entry Agent — all 5 tools on PostgreSQL."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, JournalEntry, BankTransaction, BankAccount, PettyCashFund
from tools.schemas import CheckCashPositionInput, RecordTransactionNLInput, CheckBankTransactionsInput, ManagePettyCashInput, ProcessReceiptImageInput
from tools.cash_tools import check_cash_position
from tools.transaction_tools import record_transaction_nl
from tools.bank_tools import check_bank_transactions
from tools.petty_cash_tools import manage_petty_cash
from tools.receipt_tools import process_receipt_image
from tests.test_helpers import TEST_DATABASE_URL


def run_agent_test():
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()

    today = date(2026, 7, 28)

    # Seed journal entries for cash position
    s.add(JournalEntry(entry_id="JE-SEED-001", description="Opening balance", posted_date=date(2026, 7, 1),
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="3000-Equity", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(BankAccount(account_id="BA-001", account_name="HBL Current", bank_name="HBL"))
    s.add_all([
        BankTransaction(transaction_id="BT-001", date=today - timedelta(1), description="Opening balance",
            amount=Decimal("2000000.00"), type="credit", status="cleared", account_id="BA-001", balance_after=Decimal("2000000.00")),
        BankTransaction(transaction_id="BT-002", date=today, description="Payment from client X",
            amount=Decimal("150000.00"), type="credit", status="pending", reference="INV-100",
            account_id="BA-001", balance_after=Decimal("2150000.00")),
    ])
    s.add(PettyCashFund(fund_id="PC-001", fund_name="Main Petty Cash", current_balance=Decimal("5000.00")))
    s.commit()

    results = []

    print("=" * 70)
    print("DAILY ENTRY AGENT — FULL INTEGRATION TEST (PostgreSQL)")
    print("=" * 70)

    # Scenario 1: Cash position
    print("\n[1] User asks: \"What's our cash position today?\"")
    r1 = check_cash_position(CheckCashPositionInput(as_of_date=today), s)
    assert r1.closing_balance == Decimal("500000.00"), f"Expected 500000, got {r1.closing_balance}"
    print(f"  -> Cash balance: PKR {r1.closing_balance:,.2f}")
    results.append(("Check cash position", True))

    # Scenario 2: Record transaction
    print("\n[2] User says: \"Record office rent 50000 for July\"")
    r2 = record_transaction_nl(RecordTransactionNLInput(description="Office rent 50000 for July", posted_date=today), s)
    assert r2.status == "posted"
    assert r2.debit_account == "6000-Office Rent"
    print(f"  -> Journal entry {r2.entry_id}: Dr {r2.debit_account} {r2.debit_amount}, Cr {r2.credit_account} {r2.credit_amount}")
    results.append(("Record transaction NL", True))

    # Scenario 3: Bank transactions
    print("\n[3] User asks: \"Show me today's bank transactions\"")
    r3 = check_bank_transactions(CheckBankTransactionsInput(from_date=today, to_date=today, account_id="BA-001"), s)
    assert r3.total_count >= 1
    print(f"  -> Found {r3.total_count} transaction(s), latest: {r3.transactions[0].description}")
    results.append(("Check bank transactions", True))

    # Scenario 4: Petty cash expense
    print("\n[4] User says: \"Record petty cash expense 2000 for office supplies paid by Ali\"")
    r4 = manage_petty_cash(ManagePettyCashInput(action="expense", fund_id="PC-001", amount=Decimal("2000.00"),
        description="Office supplies", paid_by="Ali"), s)
    assert r4.needs_replenishment == True
    print(f"  -> Balance: PKR {r4.current_balance:,.2f}. Alert: {r4.message}")
    results.append(("Manage petty cash expense", True))

    # Scenario 5: Upload receipt
    print("\n[5] User uploads a receipt photo for groceries")
    r5 = process_receipt_image(ProcessReceiptImageInput(image_data="iVBORw0KGgoAAAANSUhEUgAA...", image_filename="groceries.jpg"), s)
    assert r5.status == "extracted_pending_approval"
    assert r5.confidence > 0.6
    assert r5.needs_approval == True
    print(f"  -> Receipt: {r5.vendor_name}, PKR {r5.total_amount:,.2f} (confidence: {r5.confidence:.0%}, needs approval)")
    results.append(("Process receipt image", True))

    # Scenario 6: Check replenishment
    print("\n[6] User asks: \"Is replenishment needed for petty cash?\"")
    r6 = manage_petty_cash(ManagePettyCashInput(action="check_replenishment", fund_id="PC-001", replenishment_threshold=Decimal("5000.00")), s)
    assert r6.needs_replenishment == True
    print(f"  -> Balance: PKR {r6.current_balance:,.2f}. {r6.message}")
    results.append(("Check replenishment", True))

    # Scenario 7: Another transaction
    print("\n[7] User says: \"Paid electricity bill 12000\"")
    r7 = record_transaction_nl(RecordTransactionNLInput(description="Paid electricity bill 12000", posted_date=today), s)
    assert r7.debit_account == "6200-Utilities"
    print(f"  -> Journal entry {r7.entry_id}: Dr {r7.debit_account} {r7.debit_amount}")
    results.append(("Record utilities transaction", True))

    s.close()

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print("\n" + "=" * 70)
    for scenario, ok in results: print(f"  [{ok}] {scenario}")
    print(f"\nAgent 1 Integration Test: {passed}/{total} passed")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_agent_test() else 1)
