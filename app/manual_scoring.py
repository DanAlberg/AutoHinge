import sqlite3
import os
from sqlite_store import get_db_path

def collect_manual_rating() -> int:
    if os.name == "nt":
        import winsound
        winsound.MessageBeep(0x40)

    print("\n[0] Dregs | [1] Repulsive | [2] Significant Dislike")
    print("[3] Unattractive | [4] Below Average")
    print("[5] Baseline | [6] Cute (Min I'd probably respond to)")
    print("[7] Attractive | [8] Very Hot")
    print("[9] Stunning [10] Perfection")

    while True:
        val = input("\nRate this girl 0-10 (Leave blank to skip): ").strip()
        if not val: return None
        if val.isdigit() and 0 <= int(val) <= 10:
            return int(val)
        print("Invalid. Enter 0-10.")

def update_dan_rating(profile_id: int, rating: int):
    # Use the same DB path as the rest of the app
    db_path = get_db_path() 
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE profiles SET dan_rating = ? WHERE id = ?", (rating, profile_id))
        con.commit()
        print(f"[DB] Saved dan_rating: {rating} to ID: {profile_id}")