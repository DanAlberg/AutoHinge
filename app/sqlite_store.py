import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List


VISUAL_TRAIT_FIELDS: List[Tuple[str, str]] = [
    ("Face Visibility Quality", "Face_Visibility_Quality"),
    ("Photo Authenticity / Editing Level", "Photo_Authenticity_Editing_Level"),
    ("Apparent Body Fat Level", "Apparent_Body_Fat_Level"),
    ("Profile Distinctiveness", "Profile_Distinctiveness"),
    ("Apparent Build Category", "Apparent_Build_Category"),
    ("Apparent Skin Tone", "Apparent_Skin_Tone"),
    ("Apparent Ethnic Features", "Apparent_Ethnic_Features"),
    ("Hair Color", "Hair_Color"),
    ("Facial Symmetry Level", "Facial_Symmetry_Level"),
    ("Indicators of Fitness or Lifestyle", "Indicators_of_Fitness_or_Lifestyle"),
    ("Overall Visual Appeal Vibe", "Overall_Visual_Appeal_Vibe"),
    ("Apparent Age (Years)", "Apparent_Age_Years"),
    ("Attire and Style Indicators", "Attire_and_Style_Indicators"),
    ("Body Language and Expression", "Body_Language_and_Expression"),
    ("Visible Enhancements or Features", "Visible_Enhancements_or_Features"),
    ("Apparent Chest Proportions", "Apparent_Chest_Proportions"),
    ("Apparent Attractiveness Tier", "Apparent_Attractiveness_Tier"),
    ("Reasoning for attractiveness tier", "Reasoning_for_attractiveness_tier"),
    ("Facial Proportion Balance", "Facial_Proportion_Balance"),
    ("Grooming Effort Level", "Grooming_Effort_Level"),
    ("Presentation Red Flags", "Presentation_Red_Flags"),
    ("Visible Tattoo Level", "Visible_Tattoo_Level"),
    ("Visible Piercing Level", "Visible_Piercing_Level"),
    ("Short-Term / Hookup Orientation Signals", "Short_Term_Hookup_Orientation_Signals"),
]


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def get_db_path() -> str:
    return os.path.join(_repo_root(), "profiles.db")


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the SQLite database with WAL mode and the flattened profiles table.
    Schema mirrors extracted profile fields (core biometrics, prompts, poll, photos, visual traits),
    LLM2 enrichment, and long/short scores. Dedup is enforced via UNIQUE(Name COLLATE NOCASE, Age, Height_cm).
    """
    db_path = db_path or get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        # WAL for read-while-write; NORMAL synchronous for perf
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")

        # Main flattened table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY,
                -- Core extracted fields
                Name TEXT NOT NULL,
                Gender TEXT,
                Sexuality TEXT,
                Age INTEGER NOT NULL,
                Height_cm INTEGER NOT NULL,
                Location TEXT,
                Ethnicity TEXT,
                Children TEXT,
                Family_plans TEXT,
                Covid_vaccine TEXT,
                Pets TEXT,
                Zodiac_Sign TEXT,
                Job_title TEXT,
                University TEXT,
                Religious_Beliefs TEXT,
                Home_town TEXT,
                Politics TEXT,
                Languages_spoken TEXT,
                Dating_Intentions TEXT,
                Relationship_type TEXT,
                Drinking TEXT,
                Smoking TEXT,
                Marijuana TEXT,
                Drugs TEXT,
                Biometrics_Other_Text TEXT,
                prompt_1 TEXT,
                answer_1 TEXT,
                prompt_2 TEXT,
                answer_2 TEXT,
                prompt_3 TEXT,
                answer_3 TEXT,
                Poll_question TEXT,
                Poll_answer_1 TEXT,
                Poll_answer_2 TEXT,
                Poll_answer_3 TEXT,
                Other_text TEXT,
                Media_description TEXT,
                Photo1_desc TEXT,
                Photo2_desc TEXT,
                Photo3_desc TEXT,
                Photo4_desc TEXT,
                Photo5_desc TEXT,
                Photo6_desc TEXT,
                Face_Visibility_Quality TEXT,
                Photo_Authenticity_Editing_Level TEXT,
                Apparent_Body_Fat_Level TEXT,
                Profile_Distinctiveness TEXT,
                Apparent_Build_Category TEXT,
                Apparent_Skin_Tone TEXT,
                Apparent_Ethnic_Features TEXT,
                Hair_Color TEXT,
                Facial_Symmetry_Level TEXT,
                Indicators_of_Fitness_or_Lifestyle TEXT,
                Overall_Visual_Appeal_Vibe TEXT,
                Apparent_Age_Years INTEGER,
                Attire_and_Style_Indicators TEXT,
                Body_Language_and_Expression TEXT,
                Visible_Enhancements_or_Features TEXT,
                Apparent_Chest_Proportions TEXT,
                Apparent_Attractiveness_Tier TEXT,
                Reasoning_for_attractiveness_tier TEXT,
                Facial_Proportion_Balance TEXT,
                Grooming_Effort_Level TEXT,
                Presentation_Red_Flags TEXT,
                Visible_Tattoo_Level TEXT,
                Visible_Piercing_Level TEXT,
                Short_Term_Hookup_Orientation_Signals TEXT,
                -- Enrichment (profile_eval)
                home_country_iso TEXT,
                home_country_confidence REAL,
                home_country_modifier INTEGER,
                job_normalized_title TEXT,
                job_est_salary_gbp INTEGER,
                job_band TEXT,
                job_confidence REAL,
                job_band_reason TEXT,
                job_modifier INTEGER,
                university_elite INTEGER,
                matched_university_name TEXT,
                university_modifier INTEGER,
                -- Derived
                long_score INTEGER,
                short_score INTEGER,
                score_breakdown TEXT,
                timestamp TEXT,
                -- Opening messages (JSON blob of 10 generated openers)
                opening_messages_json TEXT,
                -- Opening pick (full JSON of selection) and chosen text for analysis
                opening_pick_json TEXT,
                opening_pick_text TEXT,
                -- Verdict (LIKE/DISLIKE)
                verdict TEXT,
                -- Match logging
                matched INTEGER DEFAULT 0,
                match_time TEXT
            );
            """
        )

        # Dedup: case-insensitive name + age + height_cm
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_unique
            ON profiles(Name COLLATE NOCASE, Age, Height_cm);
            """
        )
        extra_cols = [
            "long_score INTEGER",
            "short_score INTEGER",
            "score_breakdown TEXT",
            "Poll_question TEXT",
            "Poll_answer_1 TEXT",
            "Poll_answer_2 TEXT",
            "Poll_answer_3 TEXT",
            "Biometrics_Other_Text TEXT",
            "Face_Visibility_Quality TEXT",
            "Photo_Authenticity_Editing_Level TEXT",
            "Apparent_Body_Fat_Level TEXT",
            "Profile_Distinctiveness TEXT",
            "Apparent_Build_Category TEXT",
            "Apparent_Skin_Tone TEXT",
            "Apparent_Ethnic_Features TEXT",
            "Hair_Color TEXT",
            "Facial_Symmetry_Level TEXT",
            "Indicators_of_Fitness_or_Lifestyle TEXT",
            "Overall_Visual_Appeal_Vibe TEXT",
            "Apparent_Age_Years INTEGER",
            "Attire_and_Style_Indicators TEXT",
            "Body_Language_and_Expression TEXT",
            "Visible_Enhancements_or_Features TEXT",
            "Apparent_Chest_Proportions TEXT",
            "Apparent_Attractiveness_Tier TEXT",
            "Reasoning_for_attractiveness_tier TEXT",
            "Facial_Proportion_Balance TEXT",
            "Grooming_Effort_Level TEXT",
            "Presentation_Red_Flags TEXT",
            "Visible_Tattoo_Level TEXT",
            "Visible_Piercing_Level TEXT",
            "Short_Term_Hookup_Orientation_Signals TEXT",
            "opening_messages_json TEXT",
            "opening_pick_json TEXT",
            "opening_pick_text TEXT",
            "verdict TEXT",
            "matched INTEGER DEFAULT 0",
            "match_time TEXT",
        ]
        for col in extra_cols:
            try:
                cur.execute(f"ALTER TABLE profiles ADD COLUMN {col};")
            except Exception:
                pass
        con.commit()
    finally:
        con.close()


# ---------------------- Opener results logging ----------------------


def update_profile_opening_messages_json(
    profile_id: int,
    result: Dict[str, Any],
    db_path: Optional[str] = None
) -> None:
    """
    Persist the opening messages JSON (as text) onto the same profiles row.
    Stores the entire result dict under opening_messages_json.
    """
    try:
        import json
        json_text = json.dumps(result or {}, ensure_ascii=False)
    except Exception:
        json_text = "{}"
    db_path = db_path or get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE profiles SET opening_messages_json = ? WHERE id = ?",
            (json_text, int(profile_id))
        )
        con.commit()
    finally:
        con.close()


def update_profile_opening_pick(
    profile_id: int,
    result: Dict[str, Any],
    db_path: Optional[str] = None
) -> None:
    """
    Persist the opening pick:
    - opening_pick_json: full JSON result blob
    - opening_pick_text: the chosen_text extracted for easy SQL analysis
    """
    try:
        import json
        json_text = json.dumps(result or {}, ensure_ascii=False)
    except Exception:
        json_text = "{}"
    chosen_text = ""
    try:
        if isinstance(result, dict):
            ct = result.get("chosen_text")
            if isinstance(ct, str):
                chosen_text = ct.strip()
    except Exception:
        chosen_text = ""
    db_path = db_path or get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE profiles SET opening_pick_json = ?, opening_pick_text = ? WHERE id = ?",
            (json_text, chosen_text, int(profile_id))
        )
        con.commit()
    finally:
        con.close()


def update_profile_verdict(
    profile_id: int,
    verdict: str,
    db_path: Optional[str] = None
) -> None:
    """
    Persist final verdict (LIKE/DISLIKE) to the same row.
    """
    db_path = db_path or get_db_path()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE profiles SET verdict = ? WHERE id = ?",
            ((verdict or "").strip().upper(), int(profile_id))
        )
        con.commit()
    finally:
        con.close()


def update_profile_match(
    profile_id: int,
    matched: bool = True,
    match_time: Optional[str] = None,
    db_path: Optional[str] = None
) -> None:
    """
    Persist match flags onto the existing profiles row.
    match_time should be an ISO-8601 string, or None to default to now().
    """
    db_path = db_path or get_db_path()
    if match_time is None:
        match_time = datetime.now().isoformat(timespec="seconds")
    matched_val = 1 if matched else 0
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE profiles SET matched = ?, match_time = ? WHERE id = ?",
            (matched_val, match_time, int(profile_id))
        )
        con.commit()
    finally:
        con.close()


# ---------------------- Flatten helpers ----------------------

def _coerce_int(val: Any, field: str) -> int:
    try:
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str):
            s = val.strip()
            if s == "":
                raise ValueError
            return int(float(s))
    except Exception:
        raise ValueError(f"{field} must be an integer; got {val!r}")
    raise ValueError(f"{field} must be an integer; got {val!r}")


def _extract_prompts(extracted: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    """
    Map 'Profile Prompts and Answers' list to prompt_1/answer_1 .. prompt_3/answer_3.
    Accepts both nested and flat schemas.
    """
    p1 = a1 = p2 = a2 = p3 = a3 = ""
    content = extracted.get("Profile Content (Free Description)", {}) if isinstance(extracted, dict) else {}
    arr = []
    if isinstance(content, dict):
        arr = content.get("Profile Prompts and Answers") or []
    if not arr:
        arr = extracted.get("Profile Prompts and Answers") or extracted.get("profile_prompts_and_answers") or []
    if isinstance(arr, list):
        if len(arr) > 0 and isinstance(arr[0], dict):
            p1 = (arr[0].get("prompt") or "").strip()
            a1 = (arr[0].get("answer") or "").strip()
        if len(arr) > 1 and isinstance(arr[1], dict):
            p2 = (arr[1].get("prompt") or "").strip()
            a2 = (arr[1].get("answer") or "").strip()
        if len(arr) > 2 and isinstance(arr[2], dict):
            p3 = (arr[2].get("prompt") or "").strip()
            a3 = (arr[2].get("answer") or "").strip()
    return p1, a1, p2, a2, p3, a3


def _val(d: Dict[str, Any], key1: str, key2: Optional[str] = None) -> Any:
    if key1 in d:
        return d.get(key1)
    if key2 and key2 in d:
        return d.get(key2)
    # case-insensitive fallback
    lower_map = {k.lower(): k for k in d.keys()}
    if key1.lower() in lower_map:
        return d.get(lower_map[key1.lower()])
    if key2 and key2.lower() in lower_map:
        return d.get(lower_map[key2.lower()])
    return None


def _flatten_extracted(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten the structured profile JSON into flat columns.
    Height is required and becomes Height_cm (assumed already centimeters).
    Age is required integer.
    """
    if not isinstance(extracted, dict):
        extracted = {}

    core = extracted.get("Core Biometrics (Objective)", {}) if isinstance(extracted, dict) else {}
    if not isinstance(core, dict):
        core = {}
    merged = dict(extracted)
    merged.update(core)

    name = _val(merged, "Name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Name is required")

    age_raw = _val(merged, "Age")
    age = _coerce_int(age_raw, "Age")
    height_raw = _val(merged, "Height")
    height_cm = _coerce_int(height_raw, "Height")

    (prompt_1, answer_1, prompt_2, answer_2, prompt_3, answer_3) = _extract_prompts(extracted)

    content = extracted.get("Profile Content (Free Description)", {}) if isinstance(extracted, dict) else {}
    if not isinstance(content, dict):
        content = {}

    def _photo_desc(idx: int) -> str:
        key = f"Extensive Description of Photo {idx}"
        entry = content.get(key)
        if isinstance(entry, dict):
            return (entry.get("description") or "").strip()
        if isinstance(entry, str):
            return entry
        return (_val(extracted, key) or "")

    other_text = content.get("Other text on profile not covered by above")
    if not isinstance(other_text, str):
        other_text = _val(extracted, "Other text on profile not covered by above") or ""

    media_desc = content.get("Description of any non-photo media (e.g., video (identified via timestamp in top right), voice note)")
    if not isinstance(media_desc, str):
        media_desc = _val(extracted, "Description of any non-photo media (For example poll, voice note)") or ""

    poll_question = ""
    poll_answers = ["", "", ""]
    poll = content.get("Poll (optional, most profiles will not have this)")
    if isinstance(poll, dict):
        poll_question = (poll.get("question") or "").strip()
        answers = poll.get("answers") or []
        if isinstance(answers, list):
            for idx in range(min(3, len(answers))):
                ans = answers[idx]
                if isinstance(ans, dict):
                    poll_answers[idx] = (ans.get("text") or "").strip()
                elif isinstance(ans, str):
                    poll_answers[idx] = ans.strip()

    visual_root = extracted.get("Visual Analysis (Inferred From Images)", {}) if isinstance(extracted, dict) else {}
    traits = {}
    if isinstance(visual_root, dict):
        traits = visual_root.get("Inferred Visual Traits Summary") or {}
    if not isinstance(traits, dict):
        traits = {}

    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    visual_cols = {col: _clean_text(traits.get(label)) for label, col in VISUAL_TRAIT_FIELDS}
    visual_age_raw = visual_cols.get("Apparent_Age_Years")
    if visual_age_raw not in ("", None):
        import re
        m = re.search(r"\d+", str(visual_age_raw))
        if m:
            try:
                visual_cols["Apparent_Age_Years"] = int(m.group(0))
            except Exception:
                visual_cols["Apparent_Age_Years"] = None
        else:
            visual_cols["Apparent_Age_Years"] = None
    else:
        visual_cols["Apparent_Age_Years"] = None

    row = {
        "Name": name.strip(),
        "Gender": _val(merged, "Gender") or "",
        "Sexuality": _val(merged, "Sexuality") or "",
        "Age": age,
        "Height_cm": height_cm,
        "Location": _val(merged, "Location") or "",
        "Ethnicity": _val(merged, "Explicit Ethnicity") or _val(merged, "Ethnicity") or "",
        "Children": _val(merged, "Children") or "",
        "Family_plans": _val(merged, "Family plans") or _val(merged, "Family_plans") or "",
        "Covid_vaccine": _val(merged, "Covid Vaccine") or _val(merged, "Covid_vaccine") or "",
        "Pets": _val(merged, "Pets") or "",
        "Zodiac_Sign": _val(merged, "Zodiac Sign") or _val(merged, "Zodiac_Sign") or "",
        "Job_title": _val(merged, "Job title") or _val(merged, "Job_title") or "",
        "University": _val(merged, "University") or "",
        "Religious_Beliefs": _val(merged, "Religious Beliefs") or _val(merged, "Religious_Beliefs") or "",
        "Home_town": _val(merged, "Home town") or _val(merged, "Home_town") or "",
        "Politics": _val(merged, "Politics") or "",
        "Languages_spoken": _val(merged, "Languages spoken") or _val(merged, "Languages_spoken") or "",
        "Dating_Intentions": _val(merged, "Dating Intentions") or _val(merged, "Dating_Intentions") or "",
        "Relationship_type": _val(merged, "Relationship type") or _val(merged, "Relationship_type") or "",
        "Drinking": _val(merged, "Drinking") or "",
        "Smoking": _val(merged, "Smoking") or "",
        "Marijuana": _val(merged, "Marijuana") or "",
        "Drugs": _val(merged, "Drugs") or "",
        "Biometrics_Other_Text": _val(merged, "Biometrics Other Text") or _val(merged, "Biometrics_Other_Text") or "",
        "prompt_1": prompt_1,
        "answer_1": answer_1,
        "prompt_2": prompt_2,
        "answer_2": answer_2,
        "prompt_3": prompt_3,
        "answer_3": answer_3,
        "Poll_question": poll_question,
        "Poll_answer_1": poll_answers[0],
        "Poll_answer_2": poll_answers[1],
        "Poll_answer_3": poll_answers[2],
        "Other_text": other_text or "",
        "Media_description": media_desc or "",
        "Photo1_desc": _photo_desc(1),
        "Photo2_desc": _photo_desc(2),
        "Photo3_desc": _photo_desc(3),
        "Photo4_desc": _photo_desc(4),
        "Photo5_desc": _photo_desc(5),
        "Photo6_desc": _photo_desc(6),
        **visual_cols,
    }
    return row


def _flatten_enrichment(enrichment: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(enrichment, dict):
        enrichment = {}
    job = enrichment.get("job") or {}
    return {
        "home_country_iso": enrichment.get("home_country_iso") or "",
        "home_country_confidence": float(enrichment.get("home_country_confidence") or 0.0),
        "home_country_modifier": int(enrichment.get("home_country_modifier") or 0),
        "job_normalized_title": job.get("normalized_title") or "",
        "job_est_salary_gbp": int(job.get("est_salary_gbp") or 0),
        "job_band": job.get("band") or "",
        "job_confidence": float(job.get("confidence") or 0.0),
        "job_band_reason": job.get("band_reason") or "",
        "job_modifier": int(enrichment.get("job_modifier") or 0),
        "university_elite": int(enrichment.get("university_elite") or 0),
        "matched_university_name": enrichment.get("matched_university_name") or "",
        "university_modifier": int(enrichment.get("university_modifier") or 0),
    }


# ---------------------- Upsert API ----------------------

def upsert_profile_flat(
    extracted_profile: Dict[str, Any],
    enrichment: Dict[str, Any],
    long_score: int,
    short_score: int,
    score_breakdown: Optional[str] = None,
    timestamp: Optional[str] = None,
    db_path: Optional[str] = None
) -> Optional[int]:
    """
    Flatten and UPSERT a profile row.
    - Enforces UNIQUE(Name NOCASE, Age, Height_cm) with ON CONFLICT DO NOTHING.
    - Returns rowid on insert; None if conflict (duplicate).
    - Height and Age required; ValueError raised otherwise.
    """
    db_path = db_path or get_db_path()
    init_db(db_path)  # safe to call repeatedly

    core = _flatten_extracted(extracted_profile or {})
    enrich = _flatten_enrichment(enrichment or {})
    ts = timestamp or datetime.now().isoformat(timespec="seconds")

    row = {
        **core,
        **enrich,
        "long_score": int(long_score),
        "short_score": int(short_score),
        "score_breakdown": (score_breakdown or ""),
        "timestamp": ts,
    }

    # Build insert with named parameters
    visual_cols = [col for _, col in VISUAL_TRAIT_FIELDS]
    cols = [
        "Name","Gender","Sexuality","Age","Height_cm","Location","Ethnicity","Children","Family_plans",
        "Covid_vaccine","Pets","Zodiac_Sign","Job_title","University","Religious_Beliefs","Home_town",
        "Politics","Languages_spoken","Dating_Intentions","Relationship_type","Drinking","Smoking",
        "Marijuana","Drugs","Biometrics_Other_Text","prompt_1","answer_1","prompt_2","answer_2","prompt_3","answer_3",
        "Poll_question","Poll_answer_1","Poll_answer_2","Poll_answer_3",
        "Other_text","Media_description","Photo1_desc","Photo2_desc","Photo3_desc","Photo4_desc","Photo5_desc","Photo6_desc",
        *visual_cols,
        "home_country_iso","home_country_confidence","home_country_modifier","job_normalized_title","job_est_salary_gbp",
        "job_band","job_confidence","job_band_reason","job_modifier","university_elite","matched_university_name","university_modifier",
        "long_score","short_score","score_breakdown","timestamp"
    ]
    placeholders = ",".join([f":{c}" for c in cols])
    col_list = ",".join(cols)

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            INSERT INTO profiles ({col_list})
            VALUES ({placeholders})
            ON CONFLICT(Name, Age, Height_cm) DO NOTHING;
            """,
            row
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        return cur.lastrowid
    finally:
        con.close()
