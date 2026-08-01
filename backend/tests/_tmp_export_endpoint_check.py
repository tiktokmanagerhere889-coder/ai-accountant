"""Temp verification for /export endpoints (not a committed test)."""
from fastapi.testclient import TestClient
import main

c = TestClient(main.app)
r = c.get('/export/xlsx')
print('xlsx status:', r.status_code, 'len:', len(r.content))
print('ctype:', r.headers.get('content-type'))
print('disp:', r.headers.get('content-disposition'))
r2 = c.get('/export/csv')
print('csv status:', r2.status_code, 'len:', len(r2.content))
print('ctype:', r2.headers.get('content-type'))
print('disp:', r2.headers.get('content-disposition'))
r3 = c.get('/export/xlsx?agent=ledger')
print('xlsx agent=ledger status:', r3.status_code, 'len:', len(r3.content))
r4 = c.get('/export/csv?agent=tax')
print('csv agent=tax status:', r4.status_code, 'len:', len(r4.content))
r5 = c.get('/export/xlsx?agent=bogus')
print('xlsx bogus agent status:', r5.status_code, r5.json())
