#!/usr/bin/env python3

import sqlite3
import time
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from helper_functions import connect_device, ensure_adb_running, tap, swipe, get_screen_resolution
from sqlite_store import get_db_path, init_db, update_profile_match
from ui_scan import _dump_ui_xml, _parse_ui_nodes, _bounds_center, _parse_bounds, _extract_biometrics_from_nodes
from handle_matches import (
    _automated_chat_capture, 
    _update_profile_data, 
    _log_milestone,
    _fetch_matched_profiles_with_no_events,
    _fetch_active_profiles,
    _fetch_all_matched_profiles,
    _has_conversation_events,
    _handle_unmatch_menu,
    _handle_milestone_menu,
    _handle_moved_off_hinge,
    _show_event_log,
    _find_profile_by_name,
    _select_profile,
    _recalculate_all_statuses,
    _print_profiles,
    EVENT_TYPES
)

# Colors for CLI
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.OKCYAN}=== {text} ==={Colors.ENDC}")

def print_success(text: str):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_warning(text: str):
    print(f"{Colors.WARNING}! {text}{Colors.ENDC}")

def print_error(text: str):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

# -------------------------------------------------------------------------
# UI Interaction & Parsing
# -------------------------------------------------------------------------

def _ensure_matches_tab(device) -> None:
    xml = _dump_ui_xml(device)
    if not xml: return
    
    if 'content-desc="Back to Matches"' in xml:
        nodes = _parse_ui_nodes(xml)
        for n in nodes:
            if n.get("content_desc") == "Back to Matches":
                b = n.get("bounds")
                if b:
                    cx, cy = _bounds_center(b)
                    tap(device, cx, cy)
                    time.sleep(1)
                    xml = _dump_ui_xml(device)
                    break
                    
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
        for node in root.iter():
            cd = node.get("content-desc") or ""
            if cd.startswith("Matches"):
                selected = node.get("selected") == "true"
                if not selected:
                    bounds_str = node.get("bounds")
                    if bounds_str:
                        b = _parse_bounds(bounds_str)
                        if b:
                            cx, cy = _bounds_center(b)
                            print(f"{Colors.OKBLUE}Tapping Matches tab...{Colors.ENDC}")
                            tap(device, cx, cy)
                            time.sleep(2)
                return
    except Exception:
        pass

def _expand_folder(device, xml: str, folder_prefix: str) -> str:
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
        folder_node = None
        for node in root.iter():
            text = node.get("text") or ""
            if text.startswith(folder_prefix):
                folder_node = node
                break
        
        if folder_node is None: return xml
            
        fb = _parse_bounds(folder_node.get("bounds"))
        if not fb: return xml
        
        for node in root.iter():
            cd = node.get("content-desc") or ""
            if cd in ["Expand", "Collapse"]:
                b = _parse_bounds(node.get("bounds"))
                if b and abs(_bounds_center(b)[1] - _bounds_center(fb)[1]) < 100:
                    if cd == "Expand":
                        print(f"{Colors.OKBLUE}Expanding {folder_prefix}...{Colors.ENDC}")
                        cx, cy = _bounds_center(b)
                        tap(device, cx, cy)
                        time.sleep(1.5)
                        return _dump_ui_xml(device)
                    break
    except Exception:
        pass
    return xml

def _extract_profiles_from_list(xml: str) -> List[Dict[str, Any]]:
    import xml.etree.ElementTree as ET
    profiles = []
    try:
        root = ET.fromstring(xml)
        nodes = []
        for node in root.iter():
            text = (node.get("text") or "").strip()
            bounds = _parse_bounds(node.get("bounds"))
            if text and bounds:
                nodes.append({"text": text, "bounds": bounds, "y": bounds[1], "x": bounds[0]})
        
        # Sort nodes by top y-coordinate
        nodes.sort(key=lambda n: n["y"])
        ignore_prefixes = ["Your turn", "Their turn", "Hidden", "Matches", "Discover", "Standouts", "Likes You", "Profile Hub", "Inactive chats are hidden"]
        
        # In the XML, Name and Message are siblings inside a view:
        # <node index="0" text="Priyaa" .../>
        # <node index="1" text="Was styling other actors at the pit" .../>
        # They have the exact same starting X coordinate.
        
        i = 0
        while i < len(nodes) - 1:
            n1 = nodes[i]
            if any(n1["text"].startswith(p) for p in ignore_prefixes) or not n1["text"]:
                i += 1
                continue
                
            n2 = nodes[i+1]
            # Check if n2 is likely the message preview for n1.
            # Conditions: Same X coordinate (within 10px), n2 is directly below n1, and n2 is not structural.
            if abs(n2["x"] - n1["x"]) <= 10 and n2["y"] >= n1["bounds"][3] and n2["y"] - n1["bounds"][3] < 100:
                if not any(n2["text"].startswith(p) for p in ignore_prefixes):
                    profiles.append({
                        "name": n1["text"],
                        "preview": n2["text"],
                        "bounds": n1["bounds"]
                    })
                    i += 2 # Skip the matched pair
                    continue
            i += 1
    except Exception:
        pass
    return profiles

# -------------------------------------------------------------------------
# DB & Auto-Logging Logic
# -------------------------------------------------------------------------

def _get_db_profiles_active_by_name(name: str) -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        SELECT id, Name, chat_log, milestones, status, timestamp, opening_pick_text
        FROM profiles 
        WHERE matched = 1 AND Name = ? AND status IN ('my_turn', 'her_turn', 'active')
    """, (name,))
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r[0], "name": r[1], "chat_log": r[2], 
            "milestones": r[3], "status": r[4], "timestamp": r[5], "opening_pick_text": r[6]
        } for r in rows
    ]

def _disambiguate_profile(profiles: List[Dict[str, Any]], ui_preview: str) -> Optional[Dict[str, Any]]:
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]
        
    ui_clean = ui_preview.replace('\n', ' ')
    
    # Try to find the exact match via chat_log or opening text
    for p in profiles:
        c_log = json.loads(p.get("chat_log") or "[]")
        if c_log:
            last_msg = c_log[-1]["description"].replace('\n', ' ')
            if last_msg.startswith(ui_clean[:15]):
                return p
        else:
            op_text = p.get("opening_pick_text") or ""
            if op_text.startswith(ui_clean[:15]):
                return p
                
    return None

def _all_active_profiles_in_db() -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        SELECT id, Name FROM profiles 
        WHERE matched = 1 AND status IN ('my_turn', 'her_turn', 'active')
    """)
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "name": r[1]} for r in rows]

def _attempt_auto_link_profile(device, name: str, chat_log: List[Dict[str, Any]]) -> Optional[int]:
    """Attempts to auto-link a new match by matching first sent message or biometrics."""
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # 1. Simple route: Try to match by opening text
    first_sent = next((m for m in chat_log if m["event"] == "message_sent"), None)
    
    cur.execute("""
        SELECT id, opening_pick_text, Age, Height_cm
        FROM profiles 
        WHERE matched = 0 AND Name = ? AND UPPER(COALESCE(verdict, '')) IN ('LONG_PICKUP', 'SHORT_PICKUP', 'LIKE')
    """, (name,))
    candidates = cur.fetchall()
    
    if first_sent and candidates:
        first_sent_desc = first_sent["description"].strip().lower()
        for cand in candidates:
            cand_id, cand_pick, cand_age, cand_height = cand
            if cand_pick and cand_pick.strip().lower() == first_sent_desc:
                con.close()
                print_success(f"Auto-linked {name} via matching opening message!")
                return cand_id
                
    # 2. Complex route: Scroll and extract biometrics
    print_warning(f"Could not auto-link {name} via message. Attempting biometrics extraction...")
    
    # Tap "Profile" tab
    xml = _dump_ui_xml(device)
    nodes = _parse_ui_nodes(xml)
    for n in nodes:
        if n.get("text") == "  Profile  " or n.get("content_desc") == "  Profile  ":
            b = n.get("bounds")
            if b:
                cx, cy = _bounds_center(b)
                tap(device, cx, cy)
                time.sleep(1.5)
                break
                
    # Parse biometrics
    xml = _dump_ui_xml(device)
    nodes = _parse_ui_nodes(xml)
    
    # Simple bounds check for profile scroll view
    scroll_nodes = [n for n in nodes if n.get("scrollable") and n.get("bounds")]
    scroll_area = max(scroll_nodes, key=lambda n: n["bounds"][3] - n["bounds"][1])["bounds"] if scroll_nodes else (0, 0, 1080, 2400)
    
    # We might need to scroll down to see biometrics
    swipe(device, 500, 1500, 500, 500, 400)
    time.sleep(1)
    
    xml2 = _dump_ui_xml(device)
    nodes2 = _parse_ui_nodes(xml2)
    
    # Combine nodes from before and after scroll
    bio = _extract_biometrics_from_nodes(nodes + nodes2, scroll_area)
    ui_age = bio.get("Age")
    ui_height = bio.get("Height")
    
    # Tap back to "Chat"
    for n in nodes:
        if n.get("text") == "  Chat  " or n.get("content_desc") == "  Chat  ":
            b = n.get("bounds")
            if b:
                cx, cy = _bounds_center(b)
                tap(device, cx, cy)
                time.sleep(1)
                break
                
    if ui_age or ui_height:
        # Try matching candidates again
        for cand in candidates:
            cand_id, cand_pick, cand_age, cand_height = cand
            match_age = not ui_age or cand_age == ui_age
            match_height = not ui_height or cand_height == ui_height
            
            if match_age and match_height:
                con.close()
                print_success(f"Auto-linked {name} via biometrics (Age: {ui_age}, Height: {ui_height})!")
                return cand_id

    con.close()
    print_error(f"Failed to auto-link {name}.")
    return None

def _run_auto_sync():
    ensure_adb_running()
    device = connect_device("127.0.0.1")
    if not device:
        print_error("Device not found. Please connect device/emulator via ADB.")
        return

    print_header("Starting Auto-Sync")
    _ensure_matches_tab(device)
    time.sleep(1)
    
    seen_names_on_ui = set()
    
    # We will do a strict scrolling approach and group profiles by their Y-bounds relative to headers.
    
    def get_folder_y_bounds(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
        bounds_map = {}
        for n in nodes:
            txt = (n.get("text") or "")
            if txt.startswith("Your turn"):
                b = n.get("bounds")
                if b: bounds_map["Your turn"] = b[1]
            elif txt.startswith("Their turn"):
                b = n.get("bounds")
                if b: bounds_map["Their turn"] = b[1]
            elif txt.startswith("Hidden"):
                b = n.get("bounds")
                if b: bounds_map["Hidden"] = b[1]
        return bounds_map

    # Expand all folders first
    for folder in ["Your turn", "Their turn", "Hidden"]:
        xml = _dump_ui_xml(device)
        xml = _expand_folder(device, xml, folder)
    
    scrolls = 0
    max_scrolls = 15
    last_xml = ""
    
    # We will extract and process profiles as we scroll.
    while scrolls < max_scrolls:
        xml = _dump_ui_xml(device)
        if xml == last_xml:
            break # Reached bottom or stuck
        last_xml = xml
        
        nodes = _parse_ui_nodes(xml)
        
        # Determine the Y ranges for folders on this screen
        folder_y = get_folder_y_bounds(nodes)
        # If a folder isn't visible, its Y bound is effectively off-screen.
        # But we need to categorize profiles. A profile belongs to the folder header that is immediately above it.
        # If no header is above it, it belongs to the folder that carried over from the previous scroll.
        # For simplicity, we can do a global categorization based on the active expanding UI.
        
        y_your_turn = folder_y.get("Your turn", -9999)
        y_their_turn = folder_y.get("Their turn", 99999) if "Their turn" in folder_y else 99999
        y_hidden = folder_y.get("Hidden", 99999) if "Hidden" in folder_y else 99999
        
        # Because we scroll down, if Their turn and Hidden are not on screen, they are > 99999.
        # However, if we scrolled past "Their turn" and it's above the screen, we'd need to know that.
        # A simple fix: the list is always strictly ordered. 
        # But actually, processing them per-folder by expanding, processing, collapsing is much safer.
        pass # We'll rewrite the loop to be per-folder instead of one big scroll.
        break # Exit this block, rewriting below
        
    # Rewriting the safe approach:
    # 1. Collapse all folders.
    # 2. For each folder: Expand -> Scroll until bottom of folder -> Process -> Collapse.
    
    def get_current_folders_on_screen(nodes):
        folder_tops = {}
        for n in nodes:
            txt = n.get("text") or ""
            b = n.get("bounds")
            if not b: continue
            if txt.startswith("Your turn"):
                folder_tops["Your turn"] = b[3]
            elif txt.startswith("Their turn"):
                folder_tops["Their turn"] = b[3]
            elif txt.startswith("Hidden"):
                folder_tops["Hidden"] = b[3]
        return folder_tops

    # Safe scrolling process
    # Just expand them all, scroll down from top to bottom, categorizing as we go.
    # No collapsing needed if we just carefully associate Y-bounds.

    # First, scroll to top
    for _ in range(5):
        swipe(device, 500, 500, 500, 2000, 300)
    time.sleep(1)

    # Expand all folders
    for folder in ["Your turn", "Their turn", "Hidden"]:
        xml = _dump_ui_xml(device)
        _expand_folder(device, xml, folder)

    # Now scroll and extract
    scrolls = 0
    max_scrolls = 15
    last_xml = ""
    
    while scrolls < max_scrolls:
        xml = _dump_ui_xml(device)
        if xml == last_xml:
            break
        last_xml = xml
        
        nodes = _parse_ui_nodes(xml)
        
        # We need to assign each profile to the header that is immediately above it
        # If no header is above it on THIS screen, it belongs to the folder we were last in.
        
        folders_on_screen = []
        for n in nodes:
            txt = n.get("text") or ""
            b = n.get("bounds")
            if not b: continue
            if txt.startswith("Your turn"):
                folders_on_screen.append({"name": "Your turn", "y": b[3]})
            elif txt.startswith("Their turn"):
                folders_on_screen.append({"name": "Their turn", "y": b[3]})
            elif txt.startswith("Hidden"):
                folders_on_screen.append({"name": "Hidden", "y": b[3]})
                
        folders_on_screen.sort(key=lambda x: x["y"])
        
        profiles = _extract_profiles_from_list(xml)
        
        for p in profiles:
            name = p["name"]
            py = p["bounds"][1]
            
            # Determine which folder this profile is in based on screen bounds
            folder = "Your turn" # Default fallback
            
            # Find the header immediately above this profile
            for f in reversed(folders_on_screen):
                if py >= f["y"] - 10: # small buffer
                    folder = f["name"]
                    break
            else:
                # If all headers on screen are BELOW this profile, it belongs to the folder above the screen.
                if folders_on_screen and folders_on_screen[0]["name"] == "Their turn":
                    folder = "Your turn"
                elif folders_on_screen and folders_on_screen[0]["name"] == "Hidden":
                    folder = "Their turn"
                elif not folders_on_screen:
                    # If absolutely no headers are on screen, it's a long list of something.
                    # We can assume it's Hidden if we've scrolled a lot, or Their turn. 
                    # But realistically it'll be part of the last known folder.
                    pass # We will rely on previous categorization or safely assume Hidden at the bottom.
                    # To be super safe, let's keep a global variable of the "current overarching folder"
                    pass

            # Update the global "last seen folder" tracking
            global_current_folder = folder

            if name in seen_names_on_ui:
                continue
                        
            seen_names_on_ui.add(name)
            preview = p["preview"]
            bounds = p["bounds"]
            
            profs_in_db = _get_db_profiles_active_by_name(name)
            db_prof = _disambiguate_profile(profs_in_db, preview)
            
            if folder == "Hidden":
                if db_prof:
                    m_log_str = db_prof["milestones"]
                    m_log = json.loads(m_log_str) if m_log_str else []
                    is_stale = any(m["event"] == "stale" for m in m_log)
                    if not is_stale:
                        print(f"Marking {name} as stale from Hidden list...")
                        now = datetime.now().isoformat(timespec="seconds")
                        _log_milestone(db_prof["id"], "stale", now, "Auto-detected stale from Hidden list")
                    else:
                        print(f"{name} is already known as stale. Stopping Hidden list traversal.")
                        # Fast forward scrolls to exit
                        scrolls = 999
                        break
                continue
                
            needs_import = False
            is_new_match = False
            
            if not db_prof:
                # Could be a new match or failed disambiguation
                if len(profs_in_db) > 1:
                    print_warning(f"Multiple active profiles found for {name} and UI preview could not disambiguate. Skipping auto-sync for safety.")
                    continue
                needs_import = True
                is_new_match = True
            else:
                c_log_str = db_prof["chat_log"]
                c_log = json.loads(c_log_str) if c_log_str else []
                if not c_log:
                    needs_import = True
                else:
                    last_msg = c_log[-1]["description"].replace('\n', ' ')
                    ui_preview = preview.replace('\n', ' ')
                    if not last_msg.startswith(ui_preview[:15]):
                        needs_import = True
                        
            if needs_import:
                print(f"Activity detected for {Colors.BOLD}{name}{Colors.ENDC}. Importing conversation...")
                cx, cy = _bounds_center(bounds)
                tap(device, cx, cy)
                time.sleep(2)
                
                anchor_ts = None
                if db_prof and db_prof.get("chat_log"):
                    c_log = json.loads(db_prof["chat_log"])
                    if c_log:
                        anchor_ts = c_log[-1]['timestamp']
                if not anchor_ts and db_prof:
                    anchor_ts = db_prof['timestamp']
                if not anchor_ts:
                    anchor_ts = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
                
                try:
                    captured = _automated_chat_capture(name, anchor_ts)
                    
                    if not captured:
                        print_warning(f"Could not parse any messages from the chat UI for {name}. Ensure you are on the chat tab.")
                        
                    if is_new_match and captured:
                        cand_id = _attempt_auto_link_profile(device, name, captured)
                        if cand_id:
                            first_received = next((m for m in captured if m["event"] == "message_received"), None)
                            if first_received:
                                match_time = first_received["timestamp"]
                            else:
                                match_time = datetime.now().isoformat(timespec="seconds")
                                
                            update_profile_match(cand_id, matched=True, match_time=match_time)
                            print_success(f"Logged new match for {name} at {match_time}.")
                            
                            # Reload it
                            profs_in_db = _get_db_profiles_active_by_name(name)
                            db_prof = _disambiguate_profile(profs_in_db, preview)
                        else:
                            print_error(f"Could not link profile {name}. You may need to log it manually.")
                    
                    if db_prof and captured:
                        prof_id = db_prof["id"]
                        c_log_str = db_prof.get("chat_log")
                        c_log = json.loads(c_log_str) if c_log_str else []
                        
                        seen_descs = { m['description'] for m in c_log }
                        new_msgs = [c for c in captured if c['description'] not in seen_descs]
                        if new_msgs:
                            c_log.extend(new_msgs)
                            c_log.sort(key=lambda x: x['timestamp'])
                            _update_profile_data(prof_id, chat_log=c_log)
                            print_success(f"Imported {len(new_msgs)} new messages for {name}.")
                except Exception as e:
                    print_error(f"Failed to capture chat for {name}: {e}")
                
                _ensure_matches_tab(device)
                time.sleep(1)
                
        if scrolls < 999:
            swipe(device, 500, 1800, 500, 500, 500)
            time.sleep(1)
        scrolls += 1
    
    print("\nReconciling active profiles with UI lists...")
    active_in_db = _all_active_profiles_in_db()
    for prof in active_in_db:
        if prof["name"] not in seen_names_on_ui:
            print_warning(f"Profile {prof['name']} (ID {prof['id']}) is missing from UI. Not auto-unmatching for safety, but please verify.")

    print_success("Sync complete.")

# -------------------------------------------------------------------------
# UI Formatter
# -------------------------------------------------------------------------

def _print_formatted_profiles(rows: List[Dict[str, Any]], title: str):
    if not rows: return
    print(f"\n{Colors.BOLD}{Colors.OKCYAN}--- {title} ---{Colors.ENDC}")
    
    for idx, r in enumerate(rows, start=1):
        status = r.get("status")
        
        # Color coding
        color = Colors.ENDC
        if status == "my_turn":
            color = Colors.WARNING
            status_str = "[YOUR TURN]"
        elif status == "her_turn":
            color = Colors.OKGREEN
            status_str = "[HER TURN]"
        else:
            status_str = "[ACTIVE]"

        last_act = r.get("last_activity")
        dt_str = ""
        if last_act:
            try:
                dt = datetime.fromisoformat(last_act.replace('Z', '+00:00'))
                dt_str = f" | Last: {dt.strftime('%d %b %H:%M')}"
            except: pass

        c_log = json.loads(r.get("chat_log") or "[]")
        m_log = json.loads(r.get("milestones") or "[]")
        events_info = f" | Msg: {len(c_log)} | MS: {len(m_log)}" if c_log or m_log else ""
        
        print(f"[{idx}] {color}{status_str}{Colors.ENDC} {Colors.BOLD}{r['name']}{Colors.ENDC} (ID:{r['id']}, Age:{r['age']}){dt_str}{events_info}")

# -------------------------------------------------------------------------
# Main Menu Logic
# -------------------------------------------------------------------------

def _manual_log_match() -> None:
    from log_match import _fetch_candidates, _print_candidates, _select_candidate, _prompt_match_time
    from handle_matches import _parse_int_optional
    
    print_header("Log a Hinge match manually")
    name = input(f"{Colors.OKBLUE}Name (partial ok): {Colors.ENDC}").strip()
    if not name:
        print_error("Name required.")
        return

    age = _parse_int_optional(input(f"{Colors.OKBLUE}Age (optional): {Colors.ENDC}"))
    height_cm = _parse_int_optional(input(f"{Colors.OKBLUE}Height cm (optional): {Colors.ENDC}"))

    rows = _fetch_candidates(name, age, height_cm, limit=40)
    if not rows:
        print_warning("No liked profiles found for that name/filter.")
        return

    _print_candidates(rows)
    chosen = _select_candidate(rows)
    if not chosen:
        print_warning("Cancelled.")
        return

    match_time = _prompt_match_time()
    update_profile_match(int(chosen["id"]), matched=True, match_time=match_time)
    print_success(f"Logged match for id={chosen['id']} at {match_time}.")

def _unified_interactive_menu() -> None:
    _recalculate_all_statuses()
    
    while True:
        print("\n" + Colors.HEADER + "="*60 + Colors.ENDC)
        print(f"{Colors.BOLD}MATCHES MANAGER{Colors.ENDC}")
        print(Colors.HEADER + "="*60 + Colors.ENDC)
        
        new_profiles = _fetch_matched_profiles_with_no_events()
        active_profiles = _fetch_active_profiles()
        combined_list = []
        
        if new_profiles:
            _print_formatted_profiles(new_profiles, "NEW PROFILES (No events)")
            combined_list.extend(new_profiles)
            
        if active_profiles:
            active_start_idx = len(combined_list) + 1
            # Little hack to maintain index flow
            _print_formatted_profiles(active_profiles, "ACTIVE CONVERSATIONS")
            combined_list.extend(active_profiles)
            
        print("\n" + "-"*60)
        print("Options:")
        print(f"  {Colors.BOLD}S{Colors.ENDC} - Run Auto-Sync Engine")
        print(f"  {Colors.BOLD}M{Colors.ENDC} - Manually Log a Match")
        print(f"  {Colors.BOLD}All{Colors.ENDC} - View All Profiles")
        print(f"  {Colors.BOLD}[Name or ID]{Colors.ENDC} - Select a profile to manage")
        print(f"  {Colors.BOLD}Q{Colors.ENDC} - Quit")
        
        choice = input(f"\n{Colors.OKBLUE}Enter choice: {Colors.ENDC}").strip()
        
        if not choice or choice.lower() == 'q':
            break
            
        if choice.lower() == 's':
            _run_auto_sync()
            continue
            
        if choice.lower() == 'm':
            _manual_log_match()
            continue
            
        selected = None
        if choice.isdigit() and combined_list:
            idx = int(choice) - 1
            if 0 <= idx < len(combined_list):
                selected = combined_list[idx]
        elif choice.lower() == 'all':
            all_profiles = _fetch_all_matched_profiles()
            _print_profiles(all_profiles, show_events=True)
            selected = _select_profile(all_profiles)
        else:
            selected = _find_profile_by_name(choice)
            
        if selected:
            _profile_submenu(selected)

def _profile_submenu(selected: Dict[str, Any]):
    while True:
        has_conv = _has_conversation_events(selected['id'])
        print_header(f"Manage Profile: {selected['name']} (ID: {selected['id']})")
        print("1. Unmatch Profile")
        print(f"2. {'Update' if has_conv else 'Import'} Conversation manually")
        print("3. Log Milestone (Date/Off-App/Sex)")
        print("4. Quick Log: Moved Off-App")
        print("5. View Log")
        print("6. Back to Main Menu")
        
        c = input(f"\n{Colors.OKBLUE}Choice: {Colors.ENDC}").strip()
        if c == "1":
            _handle_unmatch_menu(selected)
        elif c == "2":
            if has_conv: 
                # Inline update to avoid circular dependency loop if I call it raw
                # Wait, I imported _handle_conversation_update! Actually I only imported _automated_chat_capture.
                # Let's import the rest dynamically or inline.
                from handle_matches import _handle_conversation_update, _handle_conversation_import
                if has_conv: _handle_conversation_update(selected)
                else: _handle_conversation_import(selected)
        elif c == "3":
            _handle_milestone_menu(selected)
        elif c == "4":
            _handle_moved_off_hinge(selected)
        elif c == "5":
            _show_event_log(selected)
        elif c == "6":
            break

def main() -> int:
    init_db()
    
    # Optional launch prompt
    print_header("Hinge Matches Manager")
    run_sync = input(f"Run Auto-Sync now? (y/N): ").strip().lower()
    if run_sync == 'y':
        _run_auto_sync()
        
    try:
        _unified_interactive_menu()
        return 0
    except KeyboardInterrupt:
        return 1
    except Exception as e:
        print_error(f"Fatal Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
