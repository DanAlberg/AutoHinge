import sqlite3
import json
import sys
import xml.etree.ElementTree as ET
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlite_store import get_db_path, init_db

EVENT_TYPES = {
    "unmatched_by_her": "She unmatched",
    "unmatched_by_me": "I unmatched",
    "moved_off_hinge": "Moved conversation off Hinge",
    "stale": "Conversation peters out",
    "date": "Date number",
    "sex": "Sexual encounter",
    "ended": "Ended"
}

def _parse_int_optional(raw: str) -> Optional[int]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None

def _parse_timestamp(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    formats = [
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%y %H:%M", "%d/%m/%y %H:%M:%S",
        "%d/%m %H:%M", "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%y %H:%M",
        "%d-%m-%y %H:%M:%S", "%d-%m %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S",
        "%d %b %Y %H:%M", "%d %B %Y %H:%M", "%b %d %Y %H:%M", "%B %d %Y %H:%M",
        "%d %b %H:%M", "%d %B %H:%M", "%b %d %H:%M", "%B %d %H:%M"
    ]
    now = datetime.now()
    for fmt in formats[:20]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.isoformat(timespec="seconds")
        except Exception:
            continue
    for fmt in formats[20:]:
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(year=now.year)
            if dt > now:
                dt = dt.replace(year=now.year - 1)
            return dt.isoformat(timespec="seconds")
        except Exception:
            continue
    return None

def _calculate_status(chat_log: List[Dict[str, Any]], milestones: List[Dict[str, Any]]) -> str:
    if milestones:
        last_milestone = milestones[-1]
        m_type = last_milestone.get("event")
        if m_type in ["unmatched_by_her", "unmatched_by_me", "ended"]:
            return "ended"
        if m_type == "moved_off_hinge":
            return "moved_off_hinge"

    all_events = chat_log + milestones
    if all_events:
        all_events.sort(key=lambda x: x['timestamp'])
        last_ts = all_events[-1]['timestamp']
        try:
            last_dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
            if (datetime.now().timestamp() - last_dt.timestamp()) > (14 * 86400):
                return "stale"
        except Exception:
            pass

    if chat_log:
        last_msg = chat_log[-1]
        return "her_turn" if last_msg.get("event") == "message_sent" else "my_turn"

    return "active"

def _update_profile_data(profile_id: int, chat_log: List[Dict[str, Any]] = None, milestones: List[Dict[str, Any]] = None):
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT chat_log, milestones FROM profiles WHERE id = ?", (profile_id,))
        res = cur.fetchone()
        
        current_chat = json.loads(res[0]) if res and res[0] else []
        current_milestones = json.loads(res[1]) if res and res[1] else []
        
        final_chat = chat_log if chat_log is not None else current_chat
        final_milestones = milestones if milestones is not None else current_milestones
        
        all_events = final_chat + final_milestones
        all_events.sort(key=lambda x: x['timestamp'])
        if not all_events:
            raise RuntimeError(f"LOUD FAIL: Attempted to update profile {profile_id} with no activity data.")
        
        last_act = all_events[-1]['timestamp']
        
        new_status = _calculate_status(final_chat, final_milestones)

        cur.execute("""
            UPDATE profiles 
            SET chat_log = ?, milestones = ?, last_activity = ?, status = ?
            WHERE id = ?
        """, (json.dumps(final_chat), json.dumps(final_milestones), last_act, new_status, profile_id))
        con.commit()
    finally:
        con.close()

def _log_milestone(profile_id: int, event_type: str, timestamp: str, description: str = ""):
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT milestones FROM profiles WHERE id = ?", (profile_id,))
    res = cur.fetchone()
    con.close()
    
    milestones = json.loads(res[0]) if res and res[0] else []
    milestones.append({
        "event": event_type,
        "timestamp": timestamp,
        "description": description.strip()
    })
    
    _update_profile_data(profile_id, milestones=milestones)
    print(f"✓ Logged milestone: {EVENT_TYPES.get(event_type, event_type)} at {timestamp}")

def _parse_bounds(bounds_str: str) -> Optional[Tuple[int, int, int, int]]:
    if not bounds_str: return None
    try:
        left_top, right_bottom = bounds_str.split("][")
        x1, y1 = [int(v) for v in left_top.replace("[", "").split(",")]
        x2, y2 = [int(v) for v in right_bottom.replace("]", "").split(",")]
        return x1, y1, x2, y2
    except Exception: return None

def _get_conversation_starter(profile_id: int) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT answer_1, answer_2, answer_3, opening_pick_text, opening_pick_target_id, timestamp
            FROM profiles WHERE id = ?
        """, (profile_id,))
        row = cur.fetchone()
        if not row: return []
        a1, a2, a3, pick_text, target_id, opener_ts = row
        
        starter_content = ""
        if target_id:
            idx = target_id.split('_')[-1]
            starter_content = {'1': a1, '2': a2, '3': a3}.get(idx, "")
            
        log = []
        if starter_content:
            log.append({'event': 'message_received', 'timestamp': opener_ts, 'description': f"[Replied to Prompt]: {starter_content}"})
        if pick_text:
            log.append({'event': 'message_sent', 'timestamp': opener_ts, 'description': pick_text})
        return log
    finally:
        con.close()

def _extract_messages_from_xml(xml_content: str, match_name: str) -> List[Dict[str, Any]]:
    import re
    try:
        xml_match = re.search(r'<hierarchy.*</hierarchy>', xml_content, re.DOTALL)
        if not xml_match: return []
        root = ET.fromstring(xml_match.group(0))
    except Exception: return []

    nodes_to_sort = []
    
    for node in root.iter():
        bounds_str = node.get('bounds', '')
        bounds = _parse_bounds(bounds_str)
        
        # Screen bounds guard
        if not bounds or bounds[1] < 450 or bounds[3] > 2180:
            continue

        text = (node.get('text') or "").strip()
        desc = (node.get('content-desc') or "").strip()

        # 1. Capture Central Headers (e.g. "Thu 19 Feb 04:11")
        if text and re.search(r'\d{1,2}:\d{2}', text) and text not in ["Profile", "Chat", "Sent"]:
            nodes_to_sort.append({'type': 'TS', 'val': text, 'y': bounds[1]})
        
        # 2. Capture Chat Bubbles (Strictly prefixed)
        is_sent = desc.lower().startswith("you:")
        is_received = desc.lower().startswith(f"{match_name.lower()}:")
        
        if is_sent or is_received:
            nodes_to_sort.append({
                'type': 'MSG',
                'event': "message_sent" if is_sent else "message_received",
                'val': desc.split(':', 1)[1].strip(),
                'y': bounds[1]
            })

    # Sort strictly by Top-to-Bottom visual position
    nodes_to_sort.sort(key=lambda x: x['y'])

    current_ts = "Unknown"
    screen_messages = []
    
    for n in nodes_to_sort:
        if n['type'] == 'TS':
            current_ts = n['val']
        else:
            screen_messages.append({
                'event': n['event'],
                'timestamp': current_ts, # Pass the raw string header
                'description': n['val']
            })

    return screen_messages

def _convert_hinge_timestamp(ts_str: str) -> Optional[str]:
    if not ts_str or "Unknown" in ts_str: return None
    s = ts_str.strip()
    now = datetime.now()
    
    if s.lower().startswith("today"):
        try:
            t = datetime.strptime(s.lower().replace("today", "").strip(), "%H:%M")
            return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).isoformat(timespec="seconds")
        except: return None
        
    if s.lower().startswith("yesterday"):
        try:
            t = datetime.strptime(s.lower().replace("yesterday", "").strip(), "%H:%M")
            target = now - timedelta(days=1)
            return target.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).isoformat(timespec="seconds")
        except: return None

    formats = ["%a %d %b %H:%M", "%d/%m %H:%M", "%a %d %b %Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=now.year)
                if dt > now: dt = dt.replace(year=now.year - 1)
            return dt.isoformat(timespec="seconds")
        except: continue
    return None

def _automated_chat_capture(name: str, anchor_ts: str) -> List[Dict[str, Any]]:
    from ui_scan import _dump_ui_xml, _scroll_and_capture, _find_scroll_area, _parse_ui_nodes
    from helper_functions import ensure_adb_running, connect_device, get_screen_resolution
    
    ensure_adb_running()
    device = connect_device("127.0.0.1")
    if not device: return []
    width, height = get_screen_resolution(device)
    
    raw_messages = []
    seen_hashes = set()
    scrolls, no_move_count = 0, 0
    
    print(f"Capturing fast, stable conversation for {name}...")
    
    while scrolls < 50 and no_move_count < 3:
        xml = _dump_ui_xml(device)
        screen_messages = _extract_messages_from_xml(xml, name)
        
        new_found_this_scroll = False
        # Insert backward to maintain global top-to-bottom sequence across scrolls
        for msg in reversed(screen_messages):
            msg_hash = msg['description'] 
            
            if msg_hash not in seen_hashes:
                raw_messages.insert(0, msg)
                seen_hashes.add(msg_hash)
                new_found_this_scroll = True
        
        scroll_area = _find_scroll_area(_parse_ui_nodes(xml))
        nodes, delta = _scroll_and_capture(device, width, height, scroll_area, "up", _parse_ui_nodes(xml))
        
        scrolls += 1
        no_move_count = no_move_count + 1 if abs(delta) <= 10 else 0

    # Apply the cascading 1-minute offset globally
    final_messages = []
    last_base_ts = None
    current_dt = None

    for msg in raw_messages:
        base_ts = msg['timestamp']
        if base_ts == "Unknown":
            base_ts_iso = anchor_ts
        else:
            base_ts_iso = _convert_hinge_timestamp(base_ts) or anchor_ts

        if base_ts_iso != last_base_ts:
            last_base_ts = base_ts_iso
            current_dt = datetime.fromisoformat(base_ts_iso.replace('Z', '+00:00'))

        # Assign time and cascade by +1 minute for the next loop
        msg['timestamp'] = current_dt.isoformat(timespec="seconds")
        current_dt += timedelta(minutes=1)

        final_messages.append(msg)

    return final_messages

def _handle_conversation_import(profile: Dict[str, Any]) -> None:
    profile_id = profile["id"]
    name = profile["name"]
    
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT timestamp FROM profiles WHERE id = ?", (profile_id,))
    row = cur.fetchone()
    con.close()
    if not row or not row[0]:
        raise ValueError(f"LOUD FAIL: No Like 'timestamp' found for {name}.")
    opener_ts = row[0]
    
    captured = _automated_chat_capture(name, opener_ts)
    starter_log = _get_conversation_starter(profile_id)
    
    # Strictly filter out the starter log content from the capture to kill duplicates
    starter_descs = {m['description'] for m in starter_log}
    filtered_captured = [m for m in captured if m['description'] not in starter_descs]

    # Force the starter log into alignment with the opener_ts
    for msg in starter_log:
        msg['timestamp'] = opener_ts

    full_log = starter_log + filtered_captured
    
    _update_profile_data(profile_id, chat_log=full_log)
    print(f"✓ Imported {name}. Total messages: {len(full_log)}")

def _handle_conversation_update(profile: Dict[str, Any]) -> None:
    profile_id = profile["id"]
    name = profile["name"]
    
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT chat_log, timestamp FROM profiles WHERE id = ?", (profile_id,))
    res = cur.fetchone()
    con.close()
    
    if not res:
        raise ValueError(f"LOUD FAIL: Profile {profile_id} not found during update.")
        
    current_chat = json.loads(res[0]) if res[0] else []
    anchor_ts = current_chat[-1]['timestamp'] if current_chat else res[1]
    
    captured = _automated_chat_capture(name, anchor_ts)
    if not captured: return
    
    # Hash check based pure on string content to prevent update bleeding
    seen_descs = { m['description'] for m in current_chat }
    
    new_msgs = []
    for c in captured:
        if c['description'] not in seen_descs:
            new_msgs.append(c)

    if new_msgs:
        current_chat.extend(new_msgs)
        current_chat.sort(key=lambda x: x['timestamp'])
        _update_profile_data(profile_id, chat_log=current_chat)
        print(f"✓ Added {len(new_msgs)} new messages for {name}")
    else:
        print(f"No new messages found for {name}.")

def _fetch_matched_profiles_with_no_events(limit: int = 50) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT id, Name, Age, Height_cm, timestamp, verdict, match_time
            FROM profiles 
            WHERE matched = 1 AND (chat_log IS NULL OR chat_log = '' OR chat_log = '[]')
            AND (milestones IS NULL OR milestones = '' OR milestones = '[]')
            ORDER BY match_time DESC, timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "age": r[2], "height_cm": r[3], "timestamp": r[4], "verdict": r[5], "match_time": r[6]} for r in rows]
    finally:
        con.close()

def _fetch_all_matched_profiles(limit: int = 100) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT id, Name, Age, Height_cm, timestamp, verdict, match_time, chat_log, milestones
            FROM profiles 
            WHERE matched = 1
            ORDER BY match_time DESC, timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        return [
            {
                "id": r[0], "name": r[1], "age": r[2], "height_cm": r[3], "timestamp": r[4], 
                "verdict": r[5], "match_time": r[6], "chat_log": r[7], "milestones": r[8]
            } for r in rows
        ]
    finally:
        con.close()

def _print_profiles(rows: List[Dict[str, Any]], show_events: bool = False) -> None:
    for idx, r in enumerate(rows, start=1):
        events_info = ""
        if show_events:
            c_log = json.loads(r.get("chat_log") or "[]")
            m_log = json.loads(r.get("milestones") or "[]")
            if c_log or m_log:
                events_info = f" | Chat: {len(c_log)} | Milestones: {len(m_log)}"
        
        print(
            f"[{idx}] id={r['id']} | {r['name']} | age={r['age']} | "
            f"height_cm={r['height_cm']} | matched_at={r['match_time'] or 'N/A'} | verdict={r['verdict']}{events_info}"
        )

def _select_profile(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rows: return None
    while True:
        raw = input("Select by number or id (blank to cancel): ").strip()
        if not raw: return None
        if raw.isdigit():
            val = int(raw)
            for r in rows:
                if r["id"] == val: return r
            if 1 <= val <= len(rows): return rows[val - 1]
        print("Invalid selection.")

def _handle_unmatched(profile: Dict[str, Any], by_her: bool) -> None:
    profile_id = profile["id"]
    print(f"\nLogging: {'She unmatched' if by_her else 'I unmatched'}")
    while True:
        timestamp_input = input("Enter timestamp (or Enter for now): ").strip()
        if not timestamp_input:
            timestamp = datetime.now().isoformat(timespec="seconds")
            break
        parsed = _parse_timestamp(timestamp_input)
        if parsed:
            timestamp = parsed
            break
    description = input("Description (optional): ").strip()
    _log_milestone(profile_id, "unmatched_by_her" if by_her else "unmatched_by_me", timestamp, description)

def _handle_moved_off_hinge(profile: Dict[str, Any]) -> None:
    profile_id = profile["id"]
    print(f"\nLogging: Moved conversation off Hinge")
    while True:
        timestamp_input = input("Enter timestamp (or Enter for now): ").strip()
        if not timestamp_input:
            timestamp = datetime.now().isoformat(timespec="seconds")
            break
        parsed = _parse_timestamp(timestamp_input)
        if parsed:
            timestamp = parsed
            break
    description = input("Description (optional): ").strip()
    _log_milestone(profile_id, "moved_off_hinge", timestamp, description)

def _handle_date(profile: Dict[str, Any]) -> None:
    profile_id = profile["id"]
    while True:
        date_num_input = input("Date number (e.g., 1): ").strip()
        try:
            date_num = int(date_num_input)
            if date_num > 0: break
        except Exception: pass
    while True:
        ts_in = input("Timestamp (or Enter for now): ").strip()
        if not ts_in:
            timestamp = datetime.now().isoformat(timespec="seconds")
            break
        parsed = _parse_timestamp(ts_in)
        if parsed:
            timestamp = parsed
            break
    description = input("Description (optional): ").strip()
    full_desc = f"Date #{date_num}"
    if description: full_desc += f": {description}"
    _log_milestone(profile_id, "date", timestamp, full_desc)

def _handle_sex(profile: Dict[str, Any]) -> None:
    profile_id = profile["id"]
    while True:
        ts_in = input("Timestamp (or Enter for now): ").strip()
        if not ts_in:
            timestamp = datetime.now().isoformat(timespec="seconds")
            break
        parsed = _parse_timestamp(ts_in)
        if parsed:
            timestamp = parsed
            break
    description = input("Description (optional): ").strip()
    _log_milestone(profile_id, "sex", timestamp, description)

def _handle_stale_detection() -> None:
    """Detects and prints the names of inactive profiles before marking as stale."""
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT id, Name, last_activity FROM profiles WHERE matched = 1 AND status IN ('my_turn', 'her_turn')")
    rows = cur.fetchall()
    
    stale_profiles = []
    limit = datetime.now().timestamp() - (14 * 86400)
    
    for r in rows:
        try:
            ts = datetime.fromisoformat(r[2].replace('Z', '+00:00')).timestamp()
            if ts < limit:
                stale_profiles.append({"id": r[0], "name": r[1]})
        except Exception:
            continue
            
    if stale_profiles:
        print("\n--- Stale Profiles Detected (No activity in 14+ days) ---")
        for p in stale_profiles:
            print(f" - {p['name']} (ID: {p['id']})")
        
        if input(f"\nMark these {len(stale_profiles)} profiles as stale? (y/n): ").lower() == 'y':
            now = datetime.now().isoformat(timespec="seconds")
            for p in stale_profiles:
                _log_milestone(p['id'], "stale", now, "Auto-detected stale")
    con.close()

def _has_conversation_events(profile_id: int) -> bool:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT chat_log FROM profiles WHERE id = ?", (profile_id,))
    res = cur.fetchone()
    con.close()
    return bool(res and res[0] and res[0] != "[]")

def _show_event_log(profile: Dict[str, Any]) -> None:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT chat_log, milestones FROM profiles WHERE id = ?", (profile['id'],))
    res = cur.fetchone()
    con.close()
    chat = json.loads(res[0]) if res and res[0] else []
    miles = json.loads(res[1]) if res and res[1] else []
    print(f"\n--- Milestones for {profile['name']} ---")
    for m in miles: print(f"{m['timestamp']} - {m['event']} | {m.get('description', '')}")
    print(f"\n--- Chat History ---")
    for c in chat: print(f"{c['timestamp']} - [{'YOU' if c['event']=='message_sent' else 'HER'}]: {c['description']}")

def _handle_unmatch_menu(profile: Dict[str, Any]) -> None:
    print(f"\n--- Unmatch Profile: {profile['name']} ---")
    print("1. She unmatched")
    print("2. I unmatched")
    print("3. Back")
    c = input("Choice: ").strip()
    if c == "1": _handle_unmatched(profile, True)
    elif c == "2": _handle_unmatched(profile, False)

def _handle_milestone_menu(profile: Dict[str, Any]) -> None:
    print(f"\n--- Log Milestone: {profile['name']} ---")
    print("1. Moved off Hinge")
    print("2. Date")
    print("3. Sexual encounter")
    print("4. Back")
    c = input("Choice: ").strip()
    if c == "1": _handle_moved_off_hinge(profile)
    elif c == "2": _handle_date(profile)
    elif c == "3": _handle_sex(profile)

def _find_profile_by_name(name_query: str) -> Optional[Dict[str, Any]]:
    """Searches for profiles by name and handles duplicates."""
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # Search for all matched profiles with this name (case-insensitive)
    cur.execute("""
        SELECT id, Name, Age, Height_cm, match_time, verdict, chat_log, milestones 
        FROM profiles 
        WHERE Name LIKE ? AND matched = 1
    """, (name_query,))
    
    rows = cur.fetchall()
    con.close()
    
    if not rows:
        print(f"No match found for '{name_query}'.")
        return None

    profiles = [
        {
            "id": r[0], "name": r[1], "age": r[2], "height_cm": r[3], 
            "match_time": r[4], "verdict": r[5], "chat_log": r[6], "milestones": r[7]
        } for r in rows
    ]

    if len(profiles) == 1:
        p = profiles[0]
        print(f"\n--- Selected: {p['name']} ({p['age']}) | {p['height_cm']}cm | Matched: {p['match_time']} ---")
        return p

    # If duplicates exist, show a selection list
    print(f"\nMultiple matches found for '{name_query}':")
    _print_profiles(profiles, show_events=True)
    return _select_profile(profiles)

def _interactive_menu() -> None:
    print("\n" + "="*60 + "\nMATCH HANDLING SYSTEM\n" + "="*60)
    
    # 1. Show the "Recently Matched / No Events" list for context
    new_profiles = _fetch_matched_profiles_with_no_events()
    if new_profiles:
        print(f"\nProfiles with no events:")
        _print_profiles(new_profiles)
    
    # 2. Selection Logic (Numeric or Name-based)
    selected = None
    while not selected:
        choice = input("\nEnter name or list number (or 'all', blank to exit): ").strip()
        
        if not choice:
            return
        
        # Check if user referred to the "No Events" list by number
        if choice.isdigit() and new_profiles:
            idx = int(choice) - 1
            if 0 <= idx < len(new_profiles):
                selected = new_profiles[idx]
                print(f"\n--- Selected from list: {selected['name']} ({selected['age']}) ---")
                continue
            else:
                print(f"Number '{choice}' is out of range.")
                continue

        if choice.lower() == 'all':
            all_profiles = _fetch_all_matched_profiles()
            _print_profiles(all_profiles, show_events=True)
            selected = _select_profile(all_profiles)
            if not selected: continue
        else:
            selected = _find_profile_by_name(choice)

    # 3. Submenu Loop
    while True:
        has_conv = _has_conversation_events(selected['id'])
        print(f"\n{selected['name']} options:")
        print("1. Unmatch Profile")
        print(f"2. {'Update' if has_conv else 'Import'} Conversation")
        print("3. Milestones (Date/Off-App/Sex)")
        print("4. View Log")
        print("5. Change Profile")
        print("6. Exit")
        
        c = input("Choice: ").strip()
        if c == "1":
            _handle_unmatch_menu(selected)
        elif c == "2":
            if has_conv: _handle_conversation_update(selected)
            else: _handle_conversation_import(selected)
        elif c == "3":
            _handle_milestone_menu(selected)
        elif c == "4":
            _show_event_log(selected)
        elif c == "5":
            _interactive_menu() # Restart search
            return
        elif c == "6":
            break

def main() -> int:
    init_db()
    _handle_stale_detection()
    try:
        _interactive_menu()
        return 0
    except KeyboardInterrupt: return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())