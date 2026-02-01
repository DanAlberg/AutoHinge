#!/usr/bin/env python3

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlite_store import get_db_path, init_db, update_profile_match


LIKED_VERDICTS = ("LONG_PICKUP", "SHORT_PICKUP", "LIKE")


def _parse_int_optional(raw: str) -> Optional[int]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _parse_match_time(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None

    # Epoch seconds or milliseconds.
    if s.isdigit() and len(s) in {10, 13}:
        try:
            ts = int(s)
            if len(s) == 13:
                ts = int(ts / 1000)
            return datetime.fromtimestamp(ts).isoformat(timespec="seconds")
        except Exception:
            pass

    formats_with_year = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%d %b %Y %H:%M",
        "%d %B %Y %H:%M",
        "%b %d %Y %H:%M",
        "%B %d %Y %H:%M",
    ]
    for fmt in formats_with_year:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.isoformat(timespec="seconds")
        except Exception:
            continue

    formats_no_year = [
        "%d %b %H:%M",
        "%d %B %H:%M",
        "%b %d %H:%M",
        "%B %d %H:%M",
    ]
    now = datetime.now()
    for fmt in formats_no_year:
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(year=now.year)
            if dt > now + timedelta(days=1):
                dt = dt.replace(year=now.year - 1)
            return dt.isoformat(timespec="seconds")
        except Exception:
            continue

    return None


def _fetch_candidates(
    name: str,
    age: Optional[int],
    height_cm: Optional[int],
    limit: int = 30,
) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        where = [
            "UPPER(COALESCE(verdict, '')) IN (?,?,?)",
            "Name LIKE ? COLLATE NOCASE",
        ]
        params: List[Any] = [*LIKED_VERDICTS, f"%{name}%"]
        if age is not None:
            where.append("Age = ?")
            params.append(int(age))
        if height_cm is not None:
            where.append("Height_cm = ?")
            params.append(int(height_cm))

        sql = (
            "SELECT id, Name, Age, Height_cm, timestamp, verdict, "
            "COALESCE(matched, 0) AS matched, COALESCE(match_time, '') AS match_time "
            "FROM profiles "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY timestamp DESC "
            "LIMIT ?"
        )
        params.append(int(limit))
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "age": r[2],
                "height_cm": r[3],
                "timestamp": r[4],
                "verdict": r[5],
                "matched": r[6],
                "match_time": r[7],
            }
            for r in rows
        ]
    finally:
        con.close()


def _print_candidates(rows: List[Dict[str, Any]]) -> None:
    for idx, r in enumerate(rows, start=1):
        matched_flag = "yes" if int(r.get("matched") or 0) else "no"
        match_time = r.get("match_time") or ""
        ts = r.get("timestamp") or ""
        verdict = r.get("verdict") or ""
        print(
            f"[{idx}] id={r['id']} | {r['name']} | age={r['age']} | "
            f"height_cm={r['height_cm']} | liked_at={ts} | verdict={verdict} | "
            f"matched={matched_flag} | match_time={match_time}"
        )


def _select_candidate(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    id_map = {int(r["id"]): r for r in rows if r.get("id") is not None}
    while True:
        raw = input("Select by number or id (blank to cancel): ").strip()
        if not raw:
            return None
        if raw.isdigit():
            val = int(raw)
            if val in id_map:
                return id_map[val]
            if 1 <= val <= len(rows):
                return rows[val - 1]
        print("Invalid selection. Use the list number or the id value.")


def _prompt_match_time() -> str:
    while True:
        raw = input("Match time (e.g. 25 Jan 16:49 or 2026-01-25 16:49): ").strip()
        parsed = _parse_match_time(raw)
        if parsed:
            return parsed
        print("Could not parse time. Examples: 25 Jan 16:49 | 2026-01-25 16:49 | 2026-01-25T16:49")


def main() -> int:
    init_db()
    print("Log a Hinge match")

    name = input("Name (partial ok): ").strip()
    if not name:
        print("Name required.")
        return 1

    age = _parse_int_optional(input("Age (optional): "))
    height_cm = _parse_int_optional(input("Height cm (optional): "))

    rows = _fetch_candidates(name, age, height_cm, limit=40)
    if not rows:
        print("No liked profiles found for that name/filter.")
        return 0

    _print_candidates(rows)
    chosen = _select_candidate(rows)
    if not chosen:
        print("Cancelled.")
        return 0

    match_time = _prompt_match_time()
    update_profile_match(int(chosen["id"]), matched=True, match_time=match_time)
    print(f"Logged match for id={chosen['id']} at {match_time}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
