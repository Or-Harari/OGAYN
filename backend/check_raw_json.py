import sqlite3
import json

con = sqlite3.connect(r'C:\Users\user\dev\backend\data\backend.db')
cur = con.cursor()
rows = cur.execute('select id, name, config_json from scanner_configs where id=5').fetchall()

for r in rows:
    print(f'ID {r[0]}: {r[1]}')
    print(f'Raw config_json length: {len(r[2])}')
    print(f'Raw config_json: {r[2][:500]}...')
    config = json.loads(r[2])
    print(f'Parsed keys: {list(config.keys())}')
    print(f'recentActivity key exists: {"recentActivity" in config}')
    print(f'recentActivity value: {config.get("recentActivity")}')

con.close()
