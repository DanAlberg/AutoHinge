#!/usr/bin/env python3

import sqlite3
import json
from sqlite_store import get_db_path

def verify_import():
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute('SELECT event_log FROM profiles WHERE id = 131')
    result = cur.fetchone()
    
    if result and result[0]:
        events = json.loads(result[0])
        print(f'Yu has {len(events)} events in event log:')
        for i, e in enumerate(events, 1):
            print(f'{i}. {e["event"]}: {e["description"][:50]}...')
    else:
        print('No events found')

if __name__ == "__main__":
    verify_import()