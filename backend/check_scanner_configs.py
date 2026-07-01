import sqlite3
import json

con = sqlite3.connect(r'C:\Users\user\dev\backend\data\backend.db')
cur = con.cursor()
rows = cur.execute('select id, name, config_json from scanner_configs').fetchall()

print('Scanner configs:\n')
for r in rows:
    config = json.loads(r[2])
    ra = config.get('recent_activity', {})
    print(f'ID {r[0]}: {r[1]}')
    print(f'  recent_activity.enabled: {ra.get("enabled")}')
    print(f'  full recent_activity: {json.dumps(ra, indent=2)}')
    print()

con.close()
