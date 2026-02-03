#!/usr/bin/env python3

"""Entry point for the full Hinge scrape/score/opener pipeline."""

import argparse
import json
import os
import shutil
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config  # ensure .env is loaded early

from helper_functions import ensure_adb_running, connect_device, get_screen_resolution, open_hinge
from extraction import run_llm1_visual, run_profile_eval_llm, _build_extracted_profile
from openers import run_llm3_long, run_llm3_short, run_llm4_long, run_llm4_short
from profile_utils import _get_core, _norm_value
from runtime import _is_run_json_enabled, _log, set_verbose
from scoring import _classify_preference_flag, _format_score_table, _score_profile_long, _score_profile_short
from sqlite_store import (
    get_db_path,
    upsert_profile_flat,
    update_profile_opening_messages_json,
    update_profile_opening_pick,
    update_profile_verdict,
)
from ui_scan import (
    _bounds_visible,
    _bounds_center,
    _bounds_close,
    _clear_crops_folder,
    _compute_desired_offset,
    _dump_ui_xml,
    _ensure_photo_square,
    _find_add_comment_bounds,
    _find_like_button_in_photo,
    _find_like_button_near_bounds_screen,
    _find_like_button_near_expected,
    _find_dislike_bounds,
    _find_poll_option_bounds_by_text,
    _find_prompt_bounds_by_text,
    _find_scroll_area,
    _find_send_like_anyway_bounds,
    _find_send_priority_like_bounds,
    _find_visible_photo_bounds,
    _is_loading_screen,
    _is_square_bounds,
    _match_photo_bounds_by_hash,
    _parse_ui_nodes,
    _resolve_target_from_ui_map,
    _scan_profile_single_pass,
    _seek_photo_by_index,
    _seek_photo_by_index_from_bottom,
    _seek_target_on_screen,
)


def _force_gemini_env() -> None:
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    gemini_model = os.getenv("GEMINI_MODEL")
    gemini_small = os.getenv("GEMINI_SMALL_MODEL")
    if gemini_model and not os.getenv("LLM_MODEL"):
        os.environ["LLM_MODEL"] = gemini_model
    if gemini_small and not os.getenv("LLM_SMALL_MODEL"):
        os.environ["LLM_SMALL_MODEL"] = gemini_small
    os.environ.setdefault("HINGE_CV_DEBUG_MODE", "0")
    os.environ.setdefault("HINGE_TARGET_DEBUG", "1")
    os.environ.setdefault("HINGE_SHOW_EXTRACTION_WARNINGS", "0")


def _init_device(device_ip: str):
    ensure_adb_running()
    device = connect_device(device_ip)
    if not device:
        print("Failed to connect to device")
        return None, 0, 0
    width, height = get_screen_resolution(device)
    open_hinge(device)
    time.sleep(5)
    return device, width, height


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Hinge scrape/score/opener pipeline")
    parser.add_argument("--unrestricted", action="store_true", help="Skip confirmations for dislike/send")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose [SCROLL]/[PHOTO] logging")
    parser.add_argument(
        "--profiles",
        type=int,
        default=1,
        help="Number of profiles to process before exiting (default: 1)",
    )
    return parser.parse_args()


def _confirm_action(action_label: str, unrestricted: bool, timings: Optional[Dict[str, Any]] = None) -> bool:
    if unrestricted:
        return True
    try:
        t0 = time.perf_counter()
        resp = input(f"Confirm {action_label}? (y/N): ").strip().lower()
        if isinstance(timings, dict):
            timings["input_wait_s"] = timings.get("input_wait_s", 0.0) + (time.perf_counter() - t0)
        return resp in {"y", "yes"}
    except Exception:
        return False


def _extract_openers_list(llm3_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    openers = llm3_result.get("openers") if isinstance(llm3_result, dict) else None
    if not isinstance(openers, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for o in openers:
        if not isinstance(o, dict):
            continue
        text = (o.get("text") or "").strip()
        if not text:
            continue
        cleaned.append(
            {
                "text": text,
                "main_target_type": (o.get("main_target_type") or "").strip(),
                "main_target_id": (o.get("main_target_id") or "").strip(),
                "hook_basis": (o.get("hook_basis") or "").strip(),
            }
        )
    return cleaned


def _default_opener_index(openers: List[Dict[str, Any]], llm4_result: Dict[str, Any]) -> Optional[int]:
    if not openers:
        return None
    idx_raw = llm4_result.get("chosen_index") if isinstance(llm4_result, dict) else None
    try:
        idx = int(idx_raw)
        if 0 <= idx < len(openers):
            return idx
    except Exception:
        pass
    chosen_text = (llm4_result.get("chosen_text") or "").strip() if isinstance(llm4_result, dict) else ""
    if chosen_text:
        for i, o in enumerate(openers):
            if o.get("text") == chosen_text:
                return i
    return 0 if openers else None


def _choose_opening_message(
    llm3_result: Dict[str, Any],
    llm4_result: Dict[str, Any],
    unrestricted: bool,
    timings: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool, bool]:
    openers = _extract_openers_list(llm3_result)
    updated = dict(llm4_result or {})
    idx = _default_opener_index(openers, updated)
    if idx is not None:
        sel = openers[idx]
        updated["chosen_index"] = idx
        updated["chosen_text"] = sel.get("text", updated.get("chosen_text", ""))
        updated["main_target_type"] = sel.get("main_target_type", updated.get("main_target_type", ""))
        updated["main_target_id"] = sel.get("main_target_id", updated.get("main_target_id", ""))

    if unrestricted:
        return updated, True, False

    while True:
        chosen_text = (updated.get("chosen_text") or "").strip()
        chosen_target = (updated.get("main_target_id") or "").strip()
        chosen_idx = updated.get("chosen_index")
        idx_label = f"LLM4 #{int(chosen_idx) + 1}" if isinstance(chosen_idx, int) else "LLM4"
        print(f"[SEND] planned opener ({idx_label}, target={chosen_target or 'unknown'}): \"{chosen_text}\"")
        prompt = "Enter y to send, n to skip"
        if openers:
            prompt += ", or options"
        prompt += ", or redo, or override: "
        try:
            t0 = time.perf_counter()
            resp = input(prompt).strip().lower()
            if isinstance(timings, dict):
                timings["input_wait_s"] = timings.get("input_wait_s", 0.0) + (time.perf_counter() - t0)
        except Exception:
            return updated, False, False
        if resp in {"y", "yes"}:
            return updated, True, False
        if resp in {"n", "no", ""}:
            return updated, False, False
        if resp == "redo":
            return updated, False, True
        if resp == "override":
            try:
                t0 = time.perf_counter()
                custom_text = input("Enter custom message (blank to cancel): ").strip()
                if isinstance(timings, dict):
                    timings["input_wait_s"] = timings.get("input_wait_s", 0.0) + (time.perf_counter() - t0)
            except Exception:
                return updated, False, False
            if not custom_text:
                continue
            updated["chosen_text"] = custom_text
            updated["chosen_index"] = None
            updated["rationale"] = "override"
            continue
        if resp == "options" and openers:
            for i, o in enumerate(openers, start=1):
                tgt = o.get("main_target_id") or ""
                print(f"[SEND] {i}. ({tgt}) {o.get('text')}")
            try:
                t0 = time.perf_counter()
                pick_raw = input(f"Pick 1-{len(openers)} (blank to cancel): ").strip().lower()
                if isinstance(timings, dict):
                    timings["input_wait_s"] = timings.get("input_wait_s", 0.0) + (time.perf_counter() - t0)
            except Exception:
                return updated, False, False
            if not pick_raw:
                continue
            if pick_raw.isdigit():
                pick = int(pick_raw)
                if 1 <= pick <= len(openers):
                    sel = openers[pick - 1]
                    updated["chosen_index"] = pick - 1
                    updated["chosen_text"] = sel.get("text", updated.get("chosen_text", ""))
                    updated["main_target_type"] = sel.get("main_target_type", updated.get("main_target_type", ""))
                    updated["main_target_id"] = sel.get("main_target_id", updated.get("main_target_id", ""))
                    continue
        print("[SEND] invalid selection")


def _tap_bounds(device, bounds: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int]:
    tap_x, tap_y = _bounds_center(bounds)
    tap_x = max(0, min(width - 1, tap_x))
    tap_y = max(0, min(height - 1, tap_y))
    from helper_functions import tap
    tap(device, tap_x, tap_y)
    return tap_x, tap_y


_SEND_ANYWAY_CHECKED = False


def _handle_send_like_anyway(device, width: int, height: int) -> bool:
    global _SEND_ANYWAY_CHECKED
    if _SEND_ANYWAY_CHECKED:
        return False
    _SEND_ANYWAY_CHECKED = True
    try:
        time.sleep(0.5)
        sheet_xml = _dump_ui_xml(device)
        sheet_nodes = _parse_ui_nodes(sheet_xml)
        anyway_bounds = _find_send_like_anyway_bounds(sheet_nodes)
        if not anyway_bounds:
            return False
        print("[UPSSELL] Send Like anyway sheet detected; dismissing.")
        _tap_bounds(device, anyway_bounds, width, height)
        time.sleep(0.4)
        return True
    except Exception as e:
        print(f"[UPSSELL] failed to dismiss: {e}")
        return False


def _wait_for_loading_to_clear(
    device,
    max_wait_s: int = 3,
    interval_s: float = 1.0,
    context: str = "",
) -> bool:
    xml = _dump_ui_xml(device)
    nodes = _parse_ui_nodes(xml)
    if not _is_loading_screen(nodes):
        return True
    label = f" ({context})" if context else ""
    print(f"[LOAD] loading screen detected{label}; waiting up to {max_wait_s}s")
    for _ in range(max_wait_s):
        time.sleep(interval_s)
        xml = _dump_ui_xml(device)
        nodes = _parse_ui_nodes(xml)
        if not _is_loading_screen(nodes):
            return True
    print(f"[LOAD] loading screen stuck after {max_wait_s}s; exiting")
    return False


def _backup_db_if_configured() -> None:
    backup_dir = (os.getenv("HINGE_DB_BACKUP_DIR") or "").strip()
    if not backup_dir or not os.path.isdir(backup_dir):
        return
    try:
        src = get_db_path()
        if not os.path.isfile(src):
            return
        dst = os.path.join(backup_dir, "profiles.db")
        shutil.copy2(src, dst)
        print(f"[BACKUP] profiles.db -> {dst}")
    except Exception as e:
        print(f"[BACKUP] failed: {e}")


def _enter_comment_text(
    device,
    width: int,
    height: int,
    chosen_text: str,
    attempts: int = 3,
) -> bool:
    safe_text = "".join(ch if ord(ch) < 128 else " " for ch in (chosen_text or ""))
    last_xml = ""
    for _ in range(attempts):
        comment_bounds = None
        for _ in range(3):
            last_xml = _dump_ui_xml(device)
            post_nodes = _parse_ui_nodes(last_xml)
            comment_bounds = _find_add_comment_bounds(post_nodes)
            if comment_bounds:
                break
            time.sleep(0.2)
        if not comment_bounds:
            time.sleep(0.2)
            continue
        try:
            _tap_bounds(device, comment_bounds, width, height)
            time.sleep(0.2)
            from helper_functions import input_text, hide_keyboard
            input_text(device, safe_text.strip())
            time.sleep(0.2)
            hide_keyboard(device)
            time.sleep(0.2)
        except Exception:
            time.sleep(0.2)
            continue
        last_xml = _dump_ui_xml(device)
        post_nodes = _parse_ui_nodes(last_xml)
        if not _find_add_comment_bounds(post_nodes):
            return True
        time.sleep(0.2)
    if last_xml:
        try:
            os.makedirs("logs", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            xml_path = os.path.join("logs", f"send_comment_missing_{ts}.xml")
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(last_xml)
            _log(f"[SEND] wrote XML snapshot to {xml_path}")
        except Exception:
            pass
    return False


def _write_run_log(path: str, data: Dict[str, Any]) -> None:
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[LOG] failed to write {path}: {e}")


def _run_single_profile(
    device,
    width: int,
    height: int,
    args: argparse.Namespace,
    max_scrolls: int,
    scroll_step: int,
    profile_idx: int,
    total_profiles: int,
) -> int:
    if total_profiles > 1:
        print(f"[RUN] profile {profile_idx + 1}/{total_profiles}")
    t_start = time.perf_counter()
    timings: Dict[str, Any] = {"input_wait_s": 0.0}
    user_requested_stop = False
    irreversible_action_taken = False
    loading_stuck = False
    send_approved = True
    out_path = ""
    table_path = ""
    log_state: Dict[str, Any] = {}
    try:
        os.makedirs("logs", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{profile_idx + 1:02d}" if total_profiles > 1 else ""
        out_path = os.path.join("logs", f"rating_test_{ts}{suffix}.json")
        table_path = os.path.join("logs", f"rating_test_{ts}{suffix}.txt")
        log_state = {
            "meta": {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "llm_provider": os.getenv("LLM_PROVIDER", ""),
                "model": os.getenv("LLM_SMALL_MODEL") or os.getenv("GEMINI_SMALL_MODEL") or "",
                "images_count": None,
                "images_paths": [],
                "timings": {},
                "scoring_ruleset": "long_v0",
            },
            "biometrics": {},
            "ui_map_summary": {},
            "llm1_result": {},
            "llm1_meta": {},
            "extracted_profile": {},
            "profile_eval": {},
            "long_score_result": {},
            "short_score_result": {},
            "score_table_long": "",
            "score_table_short": "",
            "score_table": "",
            "gate_decision": "",
            "gate_metrics": {},
            "manual_override": "",
            "llm3_variant": "",
            "llm3_result": {},
            "llm4_result": {},
            "target_action": {},
        }
        _write_run_log(out_path, log_state)
    except Exception as e:
        print(f"[LOG] failed to init run log: {e}")
    _clear_crops_folder()
    if not _wait_for_loading_to_clear(device, context="start"):
        return 3
    _log("[UI] Single-pass scan (slow scroll, capture as you go)...")
    t0 = time.perf_counter()
    scan_result = _scan_profile_single_pass(
        device,
        width,
        height,
        max_scrolls=max_scrolls,
        scroll_step_px=scroll_step,
    )
    timings["scan_s"] = round(time.perf_counter() - t0, 2)
    ui_map = scan_result.get("ui_map", {})
    biometrics = scan_result.get("biometrics", {})
    ui_photos = ui_map.get("photos", [])
    llm1_photo_entries = [
        p for p in ui_photos
        if (p.get("media_type") or "photo").lower() == "photo" and p.get("crop_path")
    ]
    photo_paths = [p.get("crop_path") for p in llm1_photo_entries]
    llm1_photo_id_map = [p.get("id") for p in llm1_photo_entries if p.get("id")]
    scroll_offset = int(scan_result.get("scroll_offset", 0))
    scroll_area = scan_result.get("scroll_area")
    scan_nodes = scan_result.get("nodes")
    if log_state:
        log_state["biometrics"] = biometrics
        log_state["ui_map_summary"] = {
            "prompts": len(ui_map.get("prompts", [])),
            "photos": len(ui_map.get("photos", [])),
            "poll_options": len(ui_map.get("poll", {}).get("options", [])),
        }
        _write_run_log(out_path, log_state)

    _log(f"[LLM1] Sending {len(photo_paths)} photos for visual analysis")
    t0 = time.perf_counter()
    llm1_result, llm1_meta = run_llm1_visual(
        photo_paths,
        model=os.getenv("LLM_SMALL_MODEL") or os.getenv("GEMINI_SMALL_MODEL") or None,
    )
    if isinstance(llm1_meta, dict):
        llm1_meta["photo_id_map"] = llm1_photo_id_map
    timings["llm1_s"] = round(time.perf_counter() - t0, 2)
    if log_state:
        log_state["llm1_result"] = llm1_result
        log_state["llm1_meta"] = llm1_meta
        meta = log_state.get("meta") or {}
        meta["images_count"] = llm1_meta.get("images_count")
        meta["images_paths"] = llm1_meta.get("images_paths", []) or photo_paths
        log_state["meta"] = meta
        _write_run_log(out_path, log_state)
    extracted = _build_extracted_profile(biometrics, ui_map, llm1_result, llm1_meta)
    if log_state:
        log_state["extracted_profile"] = extracted
        _write_run_log(out_path, log_state)

    t0 = time.perf_counter()
    eval_result = run_profile_eval_llm(
        extracted,
        model=os.getenv("LLM_SMALL_MODEL") or os.getenv("GEMINI_SMALL_MODEL") or None,
    )
    timings["llm2_s"] = round(time.perf_counter() - t0, 2)
    if log_state:
        log_state["profile_eval"] = eval_result
        _write_run_log(out_path, log_state)
    long_score_result = _score_profile_long(extracted, eval_result)
    short_score_result = _score_profile_short(extracted, eval_result)
    score_table_long = _format_score_table("Long", long_score_result)
    score_table_short = _format_score_table("Short", short_score_result)
    score_table = score_table_long + "\n\n" + score_table_short
    if log_state:
        log_state["long_score_result"] = long_score_result
        log_state["short_score_result"] = short_score_result
        log_state["score_table_long"] = score_table_long
        log_state["score_table_short"] = score_table_short
        log_state["score_table"] = score_table
        _write_run_log(out_path, log_state)
    if table_path:
        try:
            with open(table_path, "w", encoding="utf-8") as f:
                f.write(score_table)
        except Exception as e:
            print(f"[LOG] failed to write {table_path}: {e}")
    long_score = long_score_result.get("score", 0) if isinstance(long_score_result, dict) else 0
    short_score = short_score_result.get("score", 0) if isinstance(short_score_result, dict) else 0

    T_LONG = 15
    T_SHORT = 20
    DOM_MARGIN = 10

    long_ok = long_score >= T_LONG
    short_ok = short_score >= T_SHORT
    long_delta = long_score - T_LONG
    short_delta = short_score - T_SHORT

    if not long_ok and not short_ok:
        decision = "reject"
    elif long_ok and (not short_ok or long_delta >= short_delta + DOM_MARGIN):
        decision = "long_pickup"
    elif short_ok and (not long_ok or short_delta >= long_delta + DOM_MARGIN):
        decision = "short_pickup"
    else:
        decision = "long_pickup"

    dating_intention = _norm_value((_get_core(extracted) or {}).get("Dating Intentions", ""))
    if dating_intention in {_norm_value("Short-term relationship")}:
        if decision == "long_pickup":
            decision = "reject"
    elif dating_intention == _norm_value("Life partner"):
        if decision == "short_pickup":
            decision = "reject"

    if log_state:
        log_state["gate_decision"] = decision
        log_state["gate_metrics"] = {
            "long_score": int(long_score),
            "short_score": int(short_score),
            "long_delta": int(long_score - T_LONG),
            "short_delta": int(short_score - T_SHORT),
            "dom_margin": int(DOM_MARGIN),
            "t_long": int(T_LONG),
            "t_short": int(T_SHORT),
        }
        _write_run_log(out_path, log_state)

    print("\n" + score_table)

    manual_override = ""
    try:
        print(
            "Gate decision pre-override: {decision} (long_score={long_score}, short_score={short_score}, "
            "long_delta={long_delta}, short_delta={short_delta})".format(
                decision=decision,
                long_score=long_score,
                short_score=short_score,
                long_delta=long_score - T_LONG,
                short_delta=short_score - T_SHORT,
            )
        )
        if not args.unrestricted:
            t0 = time.perf_counter()
            override = input("Override decision? (long/short/reject, blank to keep): ").strip().lower()
            timings["input_wait_s"] = timings.get("input_wait_s", 0.0) + (time.perf_counter() - t0)
            if override in {"long", "short", "reject"}:
                manual_override = override
                decision = {"long": "long_pickup", "short": "short_pickup", "reject": "reject"}[override]
    except Exception:
        pass
    if log_state:
        log_state["manual_override"] = manual_override
        log_state["gate_decision"] = decision
        _write_run_log(out_path, log_state)
    print(
        "GATE decision={decision} long_score={long_score} short_score={short_score} "
        "long_delta={long_delta} short_delta={short_delta} dom_margin={dom_margin}".format(
            decision=decision,
            long_score=long_score,
            short_score=short_score,
            long_delta=long_score - T_LONG,
            short_delta=short_score - T_SHORT,
            dom_margin=DOM_MARGIN,
        )
    )

    llm3_variant = ""
    llm3_result = {}
    llm4_result = {}
    target_action = {}
    if decision == "short_pickup":
        llm3_variant = "short"
    elif decision == "long_pickup":
        llm3_variant = "long"
    if log_state:
        log_state["llm3_variant"] = llm3_variant
        _write_run_log(out_path, log_state)
    if llm3_variant:
        while True:
            t0 = time.perf_counter()
            if llm3_variant == "short":
                llm3_result = run_llm3_short(extracted)
            else:
                llm3_result = run_llm3_long(extracted)
            timings["llm3_s"] = round(time.perf_counter() - t0, 2)
            if log_state:
                log_state["llm3_result"] = llm3_result
                _write_run_log(out_path, log_state)
            if not llm3_result:
                llm4_result = {}
                break
            t0 = time.perf_counter()
            if llm3_variant == "short":
                llm4_result = run_llm4_short(llm3_result)
            else:
                llm4_result = run_llm4_long(llm3_result)
            timings["llm4_s"] = round(time.perf_counter() - t0, 2)
            if log_state:
                log_state["llm4_result"] = llm4_result
                _write_run_log(out_path, log_state)
            llm4_result, send_approved, redo_requested = _choose_opening_message(
                llm3_result, llm4_result, args.unrestricted, timings
            )
            if log_state:
                log_state["llm4_result"] = llm4_result
                _write_run_log(out_path, log_state)
            if redo_requested:
                print("[SEND] redo requested; regenerating openers")
                continue
            break
    if llm3_result:
        if not send_approved:
            print("[SEND] skipped by user; ending run after this profile")
            user_requested_stop = True
        target_id = str(llm4_result.get("main_target_id", "") or "").strip()
        if send_approved and target_id:
            print(f"[TARGET] LLM4 chose target_id={target_id}")
            target_info = _resolve_target_from_ui_map(ui_map, target_id)
            target_action = {"target_id": target_id, **target_info}
            target_type = target_info.get("type", "")
            if target_type == "photo":
                target_hash = target_info.get("photo_hash")
                target_index = None
                try:
                    target_index = int(str(target_id).split("_", 1)[1])
                except Exception:
                    target_index = None
                total_photos = len(ui_map.get("photos", []))
                if target_hash is None or not scroll_area:
                    print("[TARGET] missing photo hash or scroll area; skipping tap")
                elif not target_index:
                    print("[TARGET] missing photo index; skipping tap")
                else:
                    seek_photo = _seek_photo_by_index_from_bottom(
                        device,
                        width,
                        height,
                        scroll_area,
                        scan_nodes,
                        scroll_offset,
                        int(target_index),
                        total_photos,
                        target_hash=int(target_hash),
                    )
                    cur_nodes = seek_photo.get("nodes")
                    cur_scroll_area = seek_photo.get("scroll_area") or scroll_area
                    tap_bounds = seek_photo.get("tap_bounds")
                    tap_desc = seek_photo.get("tap_desc", "Like photo")
                    if not tap_bounds:
                        print("[TARGET] reverse seek failed; falling back to top-down scan")
                        seek_photo = _seek_photo_by_index(
                            device,
                            width,
                            height,
                            scroll_area,
                            int(target_index),
                            target_hash=int(target_hash),
                        )
                        cur_nodes = seek_photo.get("nodes")
                        cur_scroll_area = seek_photo.get("scroll_area") or scroll_area
                        tap_bounds = seek_photo.get("tap_bounds")
                        tap_desc = seek_photo.get("tap_desc", "Like photo")
                    if tap_bounds:
                        print(f"[TARGET] photo tap bounds={tap_bounds} desc='{tap_desc}'")
                        try:
                            tap_x, tap_y = _tap_bounds(device, tap_bounds, width, height)
                            print(f"[TARGET] tap issued at ({tap_x}, {tap_y})")
                        except Exception as e:
                            print(f"[TARGET] tap failed: {e}")
                            tap_x, tap_y = None, None
                        if tap_x is not None:
                            target_action["tap_coords"] = [tap_x, tap_y]
                            target_action["tap_like"] = True
                        time.sleep(0.35)
                        post_xml = _dump_ui_xml(device)
                        post_nodes = _parse_ui_nodes(post_xml)
                        post_bounds, _ = _find_like_button_near_expected(
                            post_nodes, cur_scroll_area, "photo", tap_y
                        )
                        if _bounds_close(post_bounds, tap_bounds):
                            print("[TARGET] like button still present near tap (not confirmed)")
                        else:
                            print("[TARGET] like button not found near tap (likely tapped)")
                    else:
                        print("[TARGET] photo not found on-screen; skipping tap")
            elif target_info.get("abs_bounds") and scroll_area:
                target_bounds = target_info["abs_bounds"]
                focus_bounds = target_bounds
                if target_type == "photo" and target_info.get("photo_bounds"):
                    focus_bounds = target_info.get("photo_bounds")
                if target_type == "prompt" and target_info.get("prompt_bounds"):
                    focus_bounds = target_info.get("prompt_bounds")
                desired_offset = _compute_desired_offset(focus_bounds, scroll_area)
                seek = _seek_target_on_screen(
                    device,
                    width,
                    height,
                    scroll_area,
                    scroll_offset,
                    target_type,
                    target_info,
                    desired_offset,
                )
                scroll_offset = seek.get("scroll_offset", scroll_offset)
                cur_nodes = seek.get("nodes") or _parse_ui_nodes(_dump_ui_xml(device))
                cur_scroll_area = seek.get("scroll_area") or _find_scroll_area(cur_nodes) or scroll_area
                expected_screen_y = int((target_bounds[1] + target_bounds[3]) / 2 - scroll_offset)
                tap_bounds = None
                tap_desc = ""
                if target_type == "prompt":
                    prompt_bounds = seek.get("prompt_bounds")
                    if not prompt_bounds:
                        prompt_bounds = _find_prompt_bounds_by_text(
                            cur_nodes,
                            target_info.get("prompt", ""),
                            target_info.get("answer", ""),
                        )
                    if prompt_bounds and not _bounds_visible(prompt_bounds, cur_scroll_area):
                        prompt_bounds = None
                    if prompt_bounds:
                        tap_bounds, tap_desc = _find_like_button_near_bounds_screen(
                            cur_nodes, prompt_bounds, "prompt"
                        )
                        print(f"[TARGET] prompt found on-screen at {prompt_bounds}")
                    else:
                        print("[TARGET] prompt not found on-screen; falling back to expected Y")
                        tap_bounds, tap_desc = _find_like_button_near_expected(
                            cur_nodes, cur_scroll_area, "prompt", expected_screen_y
                        )
                elif target_type == "poll":
                    option_bounds = seek.get("poll_bounds")
                    if not option_bounds:
                        option_bounds = _find_poll_option_bounds_by_text(
                            cur_nodes, target_info.get("option_text", "")
                        )
                    if option_bounds:
                        tap_bounds = option_bounds
                        tap_desc = "poll_option"
                        print(f"[TARGET] poll option found on-screen at {option_bounds}")
                    else:
                        print("[TARGET] poll option not found on-screen; skipping tap")
                elif target_type == "photo":
                    target_hash = target_info.get("photo_hash")
                    target_photo_bounds = target_info.get("photo_bounds")
                    target_abs_center_y = None
                    if target_photo_bounds:
                        target_abs_center_y = int((target_photo_bounds[1] + target_photo_bounds[3]) / 2)
                        expected_screen_y = int(target_abs_center_y - scroll_offset)

                    photo_bounds = seek.get("photo_bounds")
                    if not photo_bounds and target_abs_center_y is not None:
                        photo_bounds = _find_visible_photo_bounds(
                            cur_nodes, cur_scroll_area, expected_screen_y
                        )
                    if photo_bounds:
                        cur_nodes, scroll_offset, photo_bounds = _ensure_photo_square(
                            device,
                            width,
                            height,
                            cur_scroll_area,
                            cur_nodes,
                            scroll_offset,
                            photo_bounds,
                            target_abs_center_y=target_abs_center_y,
                        )
                        cur_scroll_area = _find_scroll_area(cur_nodes) or cur_scroll_area
                        if target_abs_center_y is not None:
                            expected_screen_y = int(target_abs_center_y - scroll_offset)

                    if target_hash is None:
                        print("[TARGET] missing photo hash; skipping hash match")
                    match_bounds = seek.get("photo_match_bounds")
                    dist = None
                    if target_hash is not None and not match_bounds:
                        match_bounds, dist = _match_photo_bounds_by_hash(
                            device,
                            width,
                            height,
                            cur_nodes,
                            cur_scroll_area,
                            int(target_hash),
                            expected_screen_y=expected_screen_y,
                            max_dist=18,
                            square_only=True,
                        )
                        if match_bounds:
                            tap_bounds, tap_desc = _find_like_button_in_photo(
                                cur_nodes, match_bounds
                            )
                            print(
                                f"[TARGET] photo hash matched bounds={match_bounds} dist={dist}"
                            )

                    if not tap_bounds and photo_bounds:
                        dy = None
                        if expected_screen_y is not None:
                            dy = abs(_bounds_center(photo_bounds)[1] - expected_screen_y)
                        if _is_square_bounds(photo_bounds) and (dy is None or dy <= 220):
                            tap_bounds, tap_desc = _find_like_button_in_photo(
                                cur_nodes, photo_bounds
                            )
                            print(f"[TARGET] using closest square photo by y dist={dy}")
                    if not tap_bounds:
                        print("[TARGET] photo not found on-screen; skipping tap")
                else:
                    tap_bounds, tap_desc = _find_like_button_near_expected(
                        cur_nodes, cur_scroll_area, target_type, expected_screen_y
                    )
                if not tap_bounds:
                    if target_type in {"photo", "poll"}:
                        print(f"[TARGET] no bounds resolved for {target_type}; skipping tap")
                    else:
                        tap_bounds = (
                            target_bounds[0],
                            target_bounds[1] - scroll_offset,
                            target_bounds[2],
                            target_bounds[3] - scroll_offset,
                        )
                if tap_bounds:
                    print(f"[TARGET] tap bounds={tap_bounds} desc='{tap_desc}' expected_y={expected_screen_y}")
                    try:
                        tap_x, tap_y = _tap_bounds(device, tap_bounds, width, height)
                        print(f"[TARGET] tap issued at ({tap_x}, {tap_y})")
                    except Exception as e:
                        print(f"[TARGET] tap failed: {e}")
                        tap_x, tap_y = None, None
                    if tap_x is not None:
                        target_action["tap_coords"] = [tap_x, tap_y]
                        target_action["tap_like"] = True
                    if target_type != "poll":
                        time.sleep(0.35)
                        post_xml = _dump_ui_xml(device)
                        post_nodes = _parse_ui_nodes(post_xml)
                        post_bounds, _ = _find_like_button_near_expected(
                            post_nodes, cur_scroll_area, target_type, tap_y
                        )
                        if _bounds_close(post_bounds, tap_bounds):
                            print("[TARGET] like button still present near tap (not confirmed)")
                        else:
                            print("[TARGET] like button not found near tap (likely tapped)")
                else:
                    print("[TARGET] no tap bounds resolved; skipping tap")
            else:
                print("[TARGET] missing bounds; skipping tap")

    if decision == "reject":
        post_xml = _dump_ui_xml(device)
        post_nodes = _parse_ui_nodes(post_xml)
        dislike_bounds = _find_dislike_bounds(post_nodes)
        if dislike_bounds:
            if _confirm_action("dislike", args.unrestricted, timings):
                try:
                    tap_x, tap_y = _tap_bounds(device, dislike_bounds, width, height)
                    target_action = {"action": "dislike", "tap_coords": [tap_x, tap_y]}
                    irreversible_action_taken = True
                    if not _wait_for_loading_to_clear(device, context="post-dislike"):
                        loading_stuck = True
                except Exception as e:
                    print(f"[DISLIKE] tap failed: {e}")
            else:
                print("[DISLIKE] skipped by user")
        else:
            print("[DISLIKE] button not found")

    if log_state:
        log_state["target_action"] = target_action
        _write_run_log(out_path, log_state)

    _backup_db_if_configured()

    if decision in {"long_pickup", "short_pickup"}:
        if not send_approved:
            user_requested_stop = True
            if log_state:
                log_state["target_action"] = target_action
                _write_run_log(out_path, log_state)
            if loading_stuck:
                return 3
            return 2
        if not isinstance(llm4_result, dict):
            raise RuntimeError("LLM4 missing result; cannot send comment.")
        chosen_text = llm4_result.get("chosen_text")
        if not isinstance(chosen_text, str) or not chosen_text.strip():
            raise RuntimeError("LLM4 missing chosen_text; cannot send comment.")

        if not _enter_comment_text(device, width, height, chosen_text, attempts=3):
            raise RuntimeError("Failed to enter comment text.")

        time.sleep(0.2)
        send_bounds = None
        for attempt in range(6):
            post_xml = _dump_ui_xml(device)
            post_nodes = _parse_ui_nodes(post_xml)
            send_bounds = _find_send_priority_like_bounds(post_nodes)
            if send_bounds:
                break
            _log(f"[SEND] priority button not found (attempt {attempt + 1}/6)")
            time.sleep(0.35)

        if not send_bounds:
            try:
                os.makedirs("logs", exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                xml_path = os.path.join("logs", f"send_priority_missing_{ts}.xml")
                with open(xml_path, "w", encoding="utf-8") as f:
                    f.write(post_xml)
                _log(f"[SEND] wrote XML snapshot to {xml_path}")
            except Exception:
                pass
            # Recovery: re-focus the comment field, then retry.
            try:
                if _enter_comment_text(device, width, height, chosen_text, attempts=2):
                    time.sleep(0.2)
                    for attempt in range(4):
                        post_xml = _dump_ui_xml(device)
                        post_nodes = _parse_ui_nodes(post_xml)
                        send_bounds = _find_send_priority_like_bounds(post_nodes)
                        if send_bounds:
                            break
                        _log(f"[SEND] recovery attempt {attempt + 1}/4 failed")
                        time.sleep(0.35)
            except Exception as e:
                _log(f"[SEND] recovery failed: {e}")

        if not send_bounds:
            raise RuntimeError("Send priority like button not found.")

        if send_approved:
            try:
                tap_x, tap_y = _tap_bounds(device, send_bounds, width, height)
                target_action["comment_text"] = chosen_text.strip()
                target_action["send_priority_coords"] = [tap_x, tap_y]
                _handle_send_like_anyway(device, width, height)
                irreversible_action_taken = True
                if not _wait_for_loading_to_clear(device, context="post-send"):
                    loading_stuck = True
            except Exception as e:
                raise RuntimeError(f"Send priority like failed: {e}")
        else:
            print("[SEND] skipped by user; ending run after this profile")
            user_requested_stop = True

    if log_state:
        log_state["target_action"] = target_action
        _write_run_log(out_path, log_state)

    # SQL logging (only after irreversible action)
    if irreversible_action_taken:
        try:
            score_breakdown = (
                f"decision={decision} long_score={long_score} short_score={short_score}\n\n"
                + score_table
            )
            pid = upsert_profile_flat(
                extracted,
                eval_result,
                long_score=int(long_score),
                short_score=int(short_score),
                score_breakdown=score_breakdown,
            )
            if pid is not None:
                update_profile_verdict(pid, decision)
                if isinstance(llm3_result, dict) and llm3_result:
                    update_profile_opening_messages_json(pid, llm3_result)
                if isinstance(llm4_result, dict) and llm4_result:
                    update_profile_opening_pick(pid, llm4_result)
        except Exception as e:
            print(f"[sql] log failed: {e}")
    else:
        print("[sql] skipped (no irreversible action taken)")

    t_end = time.perf_counter()
    timings["input_wait_s"] = round(float(timings.get("input_wait_s", 0.0)), 2)
    timings["total_elapsed_s"] = round(t_end - t_start, 2)
    timings["effective_elapsed_s"] = round(
        (t_end - t_start) - float(timings.get("input_wait_s", 0.0)),
        2,
    )
    if log_state:
        meta = log_state.get("meta") or {}
        meta["timings"] = timings
        log_state["meta"] = meta
        _write_run_log(out_path, log_state)

    parts = [
        f"total_s={timings.get('total_elapsed_s')}",
        f"effective_s={timings.get('effective_elapsed_s')}",
        f"input_wait_s={timings.get('input_wait_s')}",
    ]
    for key in ("scan_s", "llm1_s", "llm2_s", "llm3_s", "llm4_s"):
        if key in timings:
            parts.append(f"{key}={timings.get(key)}")
    print("[TIMINGS] " + " ".join(parts))

    if _is_run_json_enabled():
        print(json.dumps(log_state, indent=2, ensure_ascii=False))

    if out_path:
        print(f"Wrote results to {out_path}")
        if table_path:
            print(f"Wrote score table to {table_path}")

    preference_flag = _classify_preference_flag(long_score, short_score)
    print("\n=== Preference Flag ===")
    print(
        f"classification={preference_flag} "
        f"(long_score={long_score}, short_score={short_score}, "
        "t_long=15, t_short=20, dominance_margin=10)"
    )

    try:
        def _top_contribs(score_result: Dict[str, Any], n: int = 3) -> str:
            contribs = score_result.get("contributions", []) if isinstance(score_result, dict) else []
            items = [
                (abs(int(c.get("delta", 0) or 0)), c)
                for c in contribs
                if int(c.get("delta", 0) or 0) != 0
            ]
            items.sort(key=lambda x: x[0], reverse=True)
            parts = []
            for _, c in items[:n]:
                parts.append(f"{c.get('field','')}: {c.get('value','')} ({c.get('delta','')})")
            return "; ".join(parts) if parts else "none"

        chosen_result = long_score_result if decision == "long_pickup" else short_score_result
        chosen_label = "long" if decision == "long_pickup" else ("short" if decision == "short_pickup" else "n/a")
        summary = (
            f"FINAL decision={decision} "
            f"long_score={long_score} short_score={short_score} "
            f"long_delta={long_score - T_LONG} short_delta={short_score - T_SHORT} "
            f"key_{chosen_label}_contributors={_top_contribs(chosen_result)}"
        )
        print(summary)
    except Exception:
        pass

    if loading_stuck:
        return 3

    if user_requested_stop:
        return 2

    return 0


def main() -> int:
    args = _parse_args()
    _force_gemini_env()
    set_verbose(args.verbose)

    device_ip = "127.0.0.1"
    max_scrolls = 40
    scroll_step = 900

    device, width, height = _init_device(device_ip)
    if not device or not width or not height:
        print("Device/size missing; cannot proceed.")
        return 1

    total_profiles = max(1, int(args.profiles))
    for idx in range(total_profiles):
        rc = _run_single_profile(
            device,
            width,
            height,
            args,
            max_scrolls,
            scroll_step,
            idx,
            total_profiles,
        )
        if rc == 2:
            break
        if rc:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
