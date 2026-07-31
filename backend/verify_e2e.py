"""E2E verification: 4-bucket aging + regression check on reports.
Run: cd backend && python verify_e2e.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient
from main import app
from db.database import SessionLocal
from sqlalchemy import text

client = TestClient(app)

def seed():
    db = SessionLocal()
    try:
        for t in ["statutory_registers","flagged_entries","audit_log","reconciliation_matches","reconciliation_runs","journal_entries","cash_position","chart_of_accounts","contacts","retained_earnings","fiscal_year_close"]:
            db.execute(text(f"DELETE FROM {t}"))
        db.commit()

        # Contacts
        db.execute(text("INSERT INTO contacts (contact_id,contact_name,contact_type,phone,email,address,tax_id,related_party) VALUES ('CONT-001','TechSolutions','vendor','021-1','t@t.com','Khi','NTN-1',false)"))
        db.execute(text("INSERT INTO contacts (contact_id,contact_name,contact_type,phone,email,address,tax_id,related_party) VALUES ('CONT-002','RetailMart Karachi','customer','021-2','r@r.com','Khi','NTN-2',false)"))
        db.commit()

        # Chart of accounts
        for code, name, atype in [("1000-Cash","Cash","asset"),("1100-Bank","Bank","asset"),("1200-Receivables","Accounts Receivable","asset"),("1200-Inventory","Inventory","asset"),("2000-Payables","Payables","liability"),("3000-Equity","Equity","equity"),("4000-Revenue","Sales Revenue","revenue"),("5000-COGS","COGS","expense"),("6000-Rent","Rent","expense"),("6100-Salary","Salary","expense")]:
            db.execute(text("INSERT INTO chart_of_accounts (account_code,account_name,account_type,is_active) VALUES (:c,:n,:t,1)"), {"c":code,"n":name,"t":atype})
        db.commit()

        # Revenue + expenses (base dataset)
        entries = [
            ("JE-000","Opening Capital","2026-01-01","1000-Cash",500000,"3000-Equity",500000,None),
            ("JE-001","Rent July","2026-07-01","6000-Rent",65000,"1100-Bank",65000,None),
            ("JE-002","Salary July","2026-07-28","6100-Salary",450000,"1100-Bank",450000,None),
            ("JE-003","Revenue RetailMart","2026-07-10","1100-Bank",250000,"4000-Revenue",250000,"CONT-002"),
            ("JE-004","Inv Purchase on credit","2026-07-12","1200-Inventory",180000,"2000-Payables",180000,"CONT-001"),
        ]
        for e in entries:
            db.execute(text("INSERT INTO journal_entries (entry_id,description,posted_date,debit_account,debit_amount,credit_account,credit_amount,status,reference) VALUES (:eid,:desc,CAST(:pdate AS date),:da,:damt,:ca,:camt,'posted',:ref)"), {"eid":e[0],"desc":e[1],"pdate":e[2],"da":e[3],"damt":e[4],"ca":e[5],"camt":e[6],"ref":e[7]})
        db.commit()

        # AR invoices for 4-bucket aging — as_of date 2026-07-31
        # 07-10 → 21d → current; 06-16 → 45d → 31-60; 05-17 → 75d → 61-90; 05-01 → 91d → 90+
        ar_invoices = [
            ("JE-AR-001","Invoice INV-101","2026-07-10","1200-Receivables",150000,"4000-Revenue",150000),
            ("JE-AR-002","Invoice INV-050","2026-05-01","1200-Receivables",50000,"4000-Revenue",50000),
            ("JE-AR-003","Invoice INV-202","2026-06-16","1200-Receivables",70000,"4000-Revenue",70000),
            ("JE-AR-004","Invoice INV-303","2026-05-17","1200-Receivables",90000,"4000-Revenue",90000),
        ]
        for e in ar_invoices:
            db.execute(text("INSERT INTO journal_entries (entry_id,description,posted_date,debit_account,debit_amount,credit_account,credit_amount,status,reference) VALUES (:eid,:desc,CAST(:pdate AS date),:da,:damt,:ca,:camt,'posted','CONT-002')"), {"eid":e[0],"desc":e[1],"pdate":e[2],"da":e[3],"damt":e[4],"ca":e[5],"camt":e[6]})
        db.commit()

        print("  Seeded: base dataset + 4 AR invoices (150k/50k/70k/90k = 360k total AR)")
    finally:
        db.close()

def t(name, params):
    r = client.post("/tools/execute", json={"tool_name":name,"params":params})
    d = r.json()
    if not d.get("success"):
        print(f"  {name}: ERROR {d.get('error','')[:100]}")
        return None
    return d["result"]

def test_aging_4buckets():
    print("\n=== TEST 1: get_ar_aging_report — ALL 4 BUCKETS ===")
    res = t("get_ar_aging_report", {"as_of_date":"2026-07-31"})
    if not res: return False
    b = {x["bucket_name"]: x["total_amount"] for x in res.get("buckets",[])}
    print(f"  Current: {b.get('Current')}")
    print(f"  31-60:   {b.get('31-60 days')}")
    print(f"  61-90:   {b.get('61-90 days')}")
    print(f"  90+:     {b.get('90+ days')}")
    total = res.get("total_outstanding")
    print(f"  total: {total}")
    # Expected: 150k current, 70k 31-60, 90k 61-90, 50k 90+, total 360k
    ok = (float(b.get('Current') or 0)==150000 and float(b.get('31-60 days') or 0)==70000
          and float(b.get('61-90 days') or 0)==90000 and float(b.get('90+ days') or 0)==50000
          and float(total or 0)==360000)
    print(f"  {'PASS' if ok else 'FAIL'} (expect 150/70/90/50 = 360k)")
    return ok

def test_ar_subledger():
    print("\n=== TEST 1b: get_ar_subledger — total ===")
    res = t("get_ar_subledger", {"from_date":"2026-01-01","to_date":"2026-12-31"})
    if not res: return False
    entries = res.get("entries",[])
    print(f"  entries: {len(entries)}, total_outstanding: {res.get('total_outstanding')}")
    # All 4 AR invoices grouped under CONT-002 → 360k
    ok = len(entries)==1 and float(res.get("total_outstanding") or 0)==360000
    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok

def test_trial_balance():
    print("\n=== TEST 2a: generate_trial_balance ===")
    res = t("generate_trial_balance", {"as_of_date":"2026-07-31"})
    if not res: return False
    ib = res.get("in_balance")
    print(f"  in_balance: {ib}, accounts: {len(res.get('accounts',[]))}")
    ok = ib == True
    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok

def test_profit_loss():
    print("\n=== TEST 2b: generate_profit_loss ===")
    res = t("generate_profit_loss", {"from_date":"2026-01-01","to_date":"2026-12-31"})
    if not res: return False
    rev = res.get("total_revenue"); exp = res.get("total_expenses"); net = res.get("net_income")
    print(f"  revenue: {rev}, expenses: {exp}, net: {net}")
    # Revenue: 250k (JE-003) + 360k AR (4 invoices credit 4000) = 610k
    # Expenses: 65k rent + 450k salary + 180k payables debit? No — 180k is credit side on 2000
    # Expenses from debit 5/6/8: 65k + 450k = 515k. Net = 610k - 515k = 95k
    ok = float(rev or 0)==610000 and float(net or 0)==95000
    print(f"  {'PASS' if ok else 'FAIL'} (expect rev=610k, net=95k)")
    return ok

def test_balance_sheet():
    print("\n=== TEST 2c: generate_balance_sheet ===")
    res = t("generate_balance_sheet", {"as_of_date":"2026-07-31"})
    if not res: return False
    bal = res.get("balanced")
    ta = res.get("total_assets"); tl = res.get("total_liabilities"); te = res.get("total_equity")
    print(f"  balanced: {bal}, assets: {ta}, liabilities: {tl}, equity: {te}")
    ok = bal == True
    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok

def test_ratios():
    print("\n=== TEST 2d: calculate_financial_ratios ===")
    res = t("calculate_financial_ratios", {"fiscal_year":2026})
    if not res: return False
    print(f"  ratios: {len(res.get('ratios',[]))} computed")
    ok = len(res.get("ratios",[])) >= 5
    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok

def test_spending():
    print("\n=== TEST 2e: analyze_spending_patterns ===")
    res = t("analyze_spending_patterns", {"from_date":"2026-01-01","to_date":"2026-12-31"})
    if not res: return False
    ts = res.get("total_spending")
    print(f"  total_spending: {ts}")
    # Expenses (debit 5/6/8): 65k + 450k = 515k
    ok = float(ts or 0)==515000
    print(f"  {'PASS' if ok else 'FAIL'} (expect 515k)")
    return ok

if __name__ == "__main__":
    print("=" * 60)
    print("E2E VERIFY: 4-bucket aging + report regression")
    print("=" * 60)
    seed()
    r1 = test_aging_4buckets()
    r1b = test_ar_subledger()
    r2a = test_trial_balance()
    r2b = test_profit_loss()
    r2c = test_balance_sheet()
    r2d = test_ratios()
    r2e = test_spending()
    print(f"\n{'='*60}")
    print(f"Aging4Bucket={'PASS' if r1 else 'FAIL'} | AR_Subledger={'PASS' if r1b else 'FAIL'} | TB={'PASS' if r2a else 'FAIL'} | P&L={'PASS' if r2b else 'FAIL'} | BS={'PASS' if r2c else 'FAIL'} | Ratios={'PASS' if r2d else 'FAIL'} | Spending={'PASS' if r2e else 'FAIL'}")
