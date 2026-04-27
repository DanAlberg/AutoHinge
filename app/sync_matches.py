#!/usr/bin/env python3

import sqlite3
import time
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from helper_functions import connect_device, ensure_adb_running, tap, swipe, get_screen_resolution
from sqlite_store import get_db_path, init_db
from ui_scan import _dump_ui_xml, _parse_ui_nodes, _bounds_center, _parse_bounds
from handle_matches import _automated_chat_capture, _update_profile_data, _log_milestone

def _is_matches_tab_selected(nodes: List[Dict[str, Any]]) -> bool:
    for n in nodes:
        cd = (n.get("content_desc") or "")
        if cd.startswith("Matches"):
            # Check if selected
            # the raw XML has selected="true" but `_parse_ui_nodes` doesn't extract `selected`.
            # I should just tap it to be safe, or I can read the raw XML.
            return True
    return False

def _ensure_matches_tab(device) -> None:
    xml = _dump_ui_xml(device)
    if not xml:
        return
    # Check if we're on a chat screen (has Back to Matches button)
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
    
    # Check bottom nav Matches tab
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
                            print("Tapping Matches tab...")
                            tap(device, cx, cy)
                            time.sleep(2)
                return
    except Exception as e:
        print(f"Error parsing XML for matches tab: {e}")


def _expand_folder(device, xml: str, folder_prefix: str) -> str:
    """Finds the folder header. If the icon next to it is Expand, taps it."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
        folder_node = None
        for node in root.iter():
            text = node.get("text") or ""
            if text.startswith(folder_prefix):
                folder_node = node
                break
        
        if not folder_node:
            return xml
            
        fb = _parse_bounds(folder_node.get("bounds"))
        if not fb: return xml
        
        # Find the expand/collapse icon roughly horizontally aligned
        for node in root.iter():
            cd = node.get("content-desc") or ""
            if cd in ["Expand", "Collapse"]:
                b = _parse_bounds(node.get("bounds"))
                if b and abs(_bounds_center(b)[1] - _bounds_center(fb)[1]) < 100:
                    if cd == "Expand":
                        print(f"Expanding {folder_prefix}...")
                        cx, cy = _bounds_center(b)
                        tap(device, cx, cy)
                        time.sleep(1.5)
                        return _dump_ui_xml(device)
                    break
    except Exception as e:
        print(f"Error expanding folder {folder_prefix}: {e}")
    return xml

def _extract_profiles_from_list(xml: str) -> List[Dict[str, Any]]:
    # Profile items are a group. We can look for TextViews that don't match structural names.
    # The XML structure has Name as a TextView and Message preview as a TextView below it.
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
        
        # Sort nodes by Y coordinate to process them top-to-bottom
        nodes.sort(key=lambda n: n["y"])
        
        # Ignore structural texts
        ignore_prefixes = ["Your turn", "Their turn", "Hidden", "Matches", "Discover", "Standouts", "Likes You", "Profile Hub", "Inactive chats are hidden"]
        
        for i in range(len(nodes)):
            n1 = nodes[i]
            if any(n1["text"].startswith(p) for p in ignore_prefixes):
                continue
            
            # If the next node is slightly below this one, it might be the preview
            if i + 1 < len(nodes):
                n2 = nodes[i+1]
                if any(n2["text"].startswith(p) for p in ignore_prefixes):
                    continue
                # Same profile bounds logic: usually next to each other
                if n2["y"] > n1["y"] and n2["y"] - n1["bounds"][3] < 150 and abs(n2["x"] - n1["x"]) < 50:
                    profiles.append({
                        "name": n1["text"],
                        "preview": n2["text"],
                        "bounds": n1["bounds"]
                    })
    except Exception as e:
        print(f"Error extracting profiles: {e}")
        
    return profiles

def _get_db_profile(name: str) -> Optional[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        SELECT id, Name, chat_log, milestones, status, timestamp
        FROM profiles 
        WHERE matched = 1 AND Name = ?
    """, (name,))
    row = cur.fetchone()
    con.close()
    if row:
        return {
            "id": row[0],
            "name": row[1],
            "chat_log": row[2],
            "milestones": row[3],
            "status": row[4],
            "timestamp": row[5]
        }
    return None

def _all_active_profiles_in_db() -> List[Dict[str, Any]]:
    db_path = get_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        SELECT id, Name
        FROM profiles 
        WHERE matched = 1 AND status IN ('my_turn', 'her_turn', 'active')
    """)
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "name": r[1]} for r in rows]

def sync_matches():
    ensure_adb_running()
    device = connect_device("127.0.0.1")
    if not device:
        print("Device not found")
        return

    init_db()
    
    _ensure_matches_tab(device)
    time.sleep(1)
    
    seen_names_on_ui = set()
    
    folders_to_process = ["Your turn", "Their turn", "Hidden"]
    
    for folder in folders_to_process:
        print(f"\nProcessing folder: {folder}")
        # Need to ensure we're at top of list, but UI scrolling might be complex.
        # We'll just do a few scrolls if needed, but for now let's just parse what's there and expand.
        xml = _dump_ui_xml(device)
        xml = _expand_folder(device, xml, folder)
        
        profiles = _extract_profiles_from_list(xml)
        
        for p in profiles:
            name = p["name"]
            preview = p["preview"]
            bounds = p["bounds"]
            seen_names_on_ui.add(name)
            
            db_prof = _get_db_profile(name)
            if not db_prof:
                print(f"Profile {name} not found in DB. Skipping.")
                continue
                
            prof_id = db_prof["id"]
            
            if folder == "Hidden":
                # Mark as stale if not already
                m_log_str = db_prof["milestones"]
                m_log = json.loads(m_log_str) if m_log_str else []
                is_stale = any(m["event"] == "stale" for m in m_log)
                if not is_stale:
                    print(f"Marking {name} as stale from Hidden list...")
                    now = datetime.now().isoformat(timespec="seconds")
                    _log_milestone(prof_id, "stale", now, "Auto-detected stale from Hidden list")
                else:
                    print(f"{name} is already known as stale. Stopping Hidden list traversal.")
                    break # Stop checking hidden if we hit a known stale
                continue
                
            # For Your turn / Their turn
            c_log_str = db_prof["chat_log"]
            c_log = json.loads(c_log_str) if c_log_str else []
            
            needs_import = False
            if not c_log:
                needs_import = True
            else:
                last_msg = c_log[-1]["description"].replace('\n', ' ')
                ui_preview = preview.replace('\n', ' ')
                # Simple loose match since UI truncates
                if not last_msg.startswith(ui_preview[:15]):
                    needs_import = True
                    
            if needs_import:
                print(f"New activity for {name}. Importing conversation...")
                cx, cy = _bounds_center(bounds)
                tap(device, cx, cy)
                time.sleep(2)
                
                anchor_ts = c_log[-1]['timestamp'] if c_log else db_prof['timestamp']
                
                try:
                    captured = _automated_chat_capture(name, anchor_ts)
                    if captured:
                        # Simple append
                        seen_descs = { m['description'] for m in c_log }
                        new_msgs = [c for c in captured if c['description'] not in seen_descs]
                        if new_msgs:
                            c_log.extend(new_msgs)
                            c_log.sort(key=lambda x: x['timestamp'])
                            _update_profile_data(prof_id, chat_log=c_log)
                            print(f"Imported {len(new_msgs)} new messages for {name}.")
                except Exception as e:
                    print(f"Failed to capture chat for {name}: {e}")
                
                # Tap back button
                _ensure_matches_tab(device)
                time.sleep(1)
                
                # Re-expand folders since navigating back might have reset state
                xml = _dump_ui_xml(device)
                xml = _expand_folder(device, xml, folder)
    
    # Check for unmatched
    print("\nReconciling active profiles with UI lists...")
    active_in_db = _all_active_profiles_in_db()
    for prof in active_in_db:
        if prof["name"] not in seen_names_on_ui:
            print(f"Profile {prof['name']} (ID {prof['id']}) is active in DB but missing from UI.")
            # Automatically log as unmatched by her
            now = datetime.now().isoformat(timespec="seconds")
            _log_milestone(prof['id'], "unmatched_by_her", now, "Auto-detected missing from Matches tab")

    print("\nSync complete.")

if __name__ == "__main__":
    sync_matches()
