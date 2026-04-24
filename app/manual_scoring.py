import sqlite3
import os
import csv
from datetime import datetime
from sqlite_store import get_db_path

def collect_manual_rating() -> float:
    if os.name == "nt":
        import winsound
        winsound.MessageBeep(0x40)

    print("\n[0] Dregs | [1] Unattractive | [2] Below Average")
    print("[3] Baseline/Cute | [4] Very Hot | [5] Perfection")

    while True:
        val = input("\nRate this profile 0-5 (Decimals allowed, e.g., 2.5) (Leave blank to skip): ").strip()
        if not val: return None
        try:
            f_val = float(val)
            if 0.0 <= f_val <= 5.0:
                return f_val
            print("Invalid. Enter a number between 0 and 5.")
        except ValueError:
            print("Invalid format. Enter a number like 2.5.")

def update_dan_rating(profile_id: int, rating: float):
    # Use the same DB path as the rest of the app
    db_path = get_db_path() 
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE profiles SET dan_rating = ? WHERE id = ?", (rating, profile_id))
        con.commit()
        print(f"[DB] Saved dan_rating: {rating} to ID: {profile_id}")

def log_eval_metrics(pid, name, age, manual_score, ml_score, llm_tier, llm_long, llm_short):
    csv_path = os.path.join(os.path.dirname(get_db_path()), "scoring_eval.csv")
    file_exists = os.path.isfile(csv_path)
    
    with open(csv_path, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Timestamp", "Profile_ID", "Name", "Age", 
                "Manual_Score", "ML_Score", "LLM_Tier", 
                "LLM_Long_Score", "LLM_Short_Score"
            ])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            pid, name, age,
            manual_score if manual_score is not None else "",
            ml_score if ml_score is not None else "",
            llm_tier if llm_tier is not None else "",
            llm_long, llm_short
        ])
    print(f"[CSV] Logged evaluation metrics for {name} (ID: {pid})")
