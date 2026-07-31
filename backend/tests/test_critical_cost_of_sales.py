"""CRITICAL check: "Cost of Sales" account must classify as EXPENSE, not REVENUE.
Run: cd backend && PYTHONIOENCODING=utf-8 python verify_critical.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from main import app
from db.database import SessionLocal
from sqlalchemy import text

client = TestClient(app)

def seed():
    db = SessionLocal()
    try:
        for t in ["flagged_entries","audit_log","journal_entries","cash_position","chart_of_accounts","contacts","retained_earnings","fiscal_year_close","budgets"]:
            db.execute(text(f"DELETE FROM {t}"))
        db.commit()

        # Chart of accounts — include a "Cost of Sales" account explicitly typed EXPENSE
        for code, name, atype in [
            ("1000-Cash","Cash","asset"),
            ("1100-Bank","Bank","asset"),
            ("3000-Equity","Equity","equity"),
            ("4000-Revenue","Sales Revenue","revenue"),
            ("5000-Cost of Sales","Cost of Sales","expense"),
            ("6000-Rent","Rent Expense","expense"),
            ("2000-Payables","Payables","liability"),
        ]:
            db.execute(text("INSERT INTO chart_of_accounts (account_code,account_name,account_type,is_active) VALUES (:c,:n,:t,1)"), {"c":code,"n":name,"t":atype})
        db.commit()

        # Journal entries
        entries = [
            # Revenue: credit Sales Revenue
            ("JE-001","Sales to customer","2026-07-10","1100-Bank",250000,"4000-Revenue",250000),
            # Cost of Sales: DEBIT Cost of Sales, credit Bank  (the critical one)
            ("JE-002","Cost of sales for goods","2026-07-12","5000-Cost of Sales",100000,"1100-Bank",100000),
            # Rent expense
            ("JE-003","Office rent","2026-07-01","6000-Rent",65000,"1100-Bank",65000),
        ]
        for e in entries:
            db.execute(text("INSERT INTO journal_entries (entry_id,description,posted_date,debit_account,debit_amount,credit_account,credit_amount,status) VALUES (:eid,:desc,CAST(:pdate AS date),:da,:damt,:ca,:camt,'posted')"), {"eid":e[0],"desc":e[1],"pdate":e[2],"da":e[3],"damt":e[4],"ca":e[5],"camt":e[6]})
        db.commit()
        print("  Seeded: Sales Rev 250k, Cost of Sales 100k, Rent 65k")
    finally:
        db.close()

def t(name, params):
    r = client.post("/tools/execute", json={"tool_name":name,"params":params})
    d = r.json()
    if not d.get("success"):
        print(f"  {name}: ERROR {d.get('error','')[:150]}")
        return None
    return d["result"]

def d(x): return float(x or 0)

print("=" * 60)
print("CRITICAL: 'Cost of Sales' classification")
print("=" * 60)
seed()

print("\n=== TEST 1: generate_profit_loss ===")
res = t("generate_profit_loss", {"from_date":"2026-01-01","to_date":"2026-12-31"})
if res:
    print(f"  total_revenue: {res.get('total_revenue')}")
    print(f"  total_expenses: {res.get('total_expenses')}")
    print(f"  net_income: {res.get('net_income')}")
    # Expect revenue=250k, expenses=165k (100k COS + 65k rent), net=85k
    ok = d(res.get('total_revenue'))==250000 and d(res.get('total_expenses'))==165000 and d(res.get('net_income'))==85000
    print(f"  {'PASS' if ok else 'FAIL'} (expect rev=250k, exp=165k, net=85k)")

print("\n=== TEST 2: calculate_revenue_recognition ===")
res = t("calculate_revenue_recognition", {"contract_id":"CTR-001","contract_value":"1000000","completion_percentage":"60","period":7,"fiscal_year":2026})
if res:
    print(f"  total_recognizable: {res.get('total_recognizable')}")
    ok2 = d(res.get('total_recognizable'))==600000
    print(f"  {'PASS' if ok2 else 'FAIL'} (revenue recognition unaffected = 600k)")

print("\n=== TEST 3: generate_balance_sheet ===")
res = t("generate_balance_sheet", {"as_of_date":"2026-07-31"})
if res:
    print(f"  balanced: {res.get('balanced')}, assets: {res.get('total_assets')}, liab: {res.get('total_liabilities')}, equity: {res.get('total_equity')}")
    print(f"  {'PASS' if res.get('balanced') else 'FAIL'} (expect balanced)")

print("\n=== TEST 4: calculate_financial_ratios ===")
res = t("calculate_financial_ratios", {"fiscal_year":2026})
if res:
    print(f"  ratios: {len(res.get('ratios',[]))}")
    for r_ in res.get('ratios',[]):
        if r_['name'] in ('Net Profit Margin (%)','Gross Profit Margin (%)','Current Ratio'):
            print(f"    {r_['name']} = {r_['value']}")
    print(f"  {'PASS' if len(res.get('ratios',[])) >= 5 else 'FAIL'}")

print("\n=== TEST 5: assess_financial_health ===")
res = t("assess_financial_health", {"fiscal_year":2026})
if res:
    print(f"  score: {res.get('score')}, assessment: {res.get('health_assessment')}")
    print(f"  {'PASS' if res.get('score') is not None else 'FAIL'}")

print("\n=== TEST 6: prepare_income_tax_filing ===")
res = t("prepare_income_tax_filing", {"fiscal_year":2026,"confirm":"yes"})
if res:
    print(f"  total_income: {res.get('total_income')}, total_expenses: {res.get('total_expenses')}")
    ok6 = d(res.get('total_income'))==250000 and d(res.get('total_expenses'))==165000
    print(f"  {'PASS' if ok6 else 'FAIL'} (expect income=250k, expenses=165k)")

print("\n=== TEST 7: detect_anomaly_transactions ===")
res = t("detect_anomaly_transactions", {"from_date":"2026-01-01","to_date":"2026-12-31"})
if res:
    print(f"  anomalies: {len(res.get('anomalies',[]))}")
    print(f"  {'PASS' if res is not None else 'FAIL'}")

print("\n=== DIRECT: is Cost of Sales in expense? ===")
from tools.account_utils import revenue_filter_clause, expense_filter_clause
from sqlalchemy import select
from db.models import JournalEntry
from db.database import SessionLocal
db = SessionLocal()
cos_entries = db.query(JournalEntry).filter(JournalEntry.debit_account.ilike("%cost of sales%")).all()
rev_clause = revenue_filter_clause(JournalEntry.debit_account, db)
exp_clause = expense_filter_clause(JournalEntry.debit_account, db)
rev_count = db.query(JournalEntry).filter(rev_clause).count()
exp_count = db.query(JournalEntry).filter(exp_clause).count()
print(f"  Entries matching revenue clause: {rev_count}")
print(f"  Entries matching expense clause: {exp_count}")
db.close()
