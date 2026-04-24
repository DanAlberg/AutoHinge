import os
import csv
import base64
import time
import numpy as np
import cv2
import joblib
from datetime import datetime

from llm_client import get_llm_client, get_default_model, LLMError
from prompts import LLM_AESTHETIC_EVAL
from sqlite_store import get_db_path

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EVC_MODEL_PATH = os.path.join(SCRIPT_DIR, "evc_model.pkl")
ARCFACE_SVR_PATH = os.path.join(SCRIPT_DIR, "arcface_svr.pkl")
CSV_PATH = os.path.join(os.path.dirname(get_db_path()), "scoring_eval.csv")

# Global variables to cache models in memory
_evc_model = None
_arcface_model = None
_arcface_app = None
_models_loaded = False

def _load_validation_models():
    global _evc_model, _arcface_model, _arcface_app, _models_loaded
    if _models_loaded:
        return
        
    print("[VALIDATION] Loading experimental ML models into memory...")
    if os.path.exists(EVC_MODEL_PATH):
        try:
            _evc_model = joblib.load(EVC_MODEL_PATH)
        except Exception as e:
            print(f"[VALIDATION] Warning: failed to load EVC model: {e}")
            
    if INSIGHTFACE_AVAILABLE and os.path.exists(ARCFACE_SVR_PATH):
        try:
            _arcface_model = joblib.load(ARCFACE_SVR_PATH)
            _arcface_app = FaceAnalysis(name='buffalo_l')
            _arcface_app.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as e:
            print(f"[VALIDATION] Warning: failed to load ArcFace model: {e}")
            
    _models_loaded = True

def _run_vlm_zero_shot(image_paths: list[str]) -> tuple[float, int]:
    """
    Executes a VLM call for aesthetic scoring and enforces a strict float cast.
    Returns (score, latency_ms).
    Throws an LLMError explicitly if the request is blocked, hallucinated, or malformed.
    """
    client = get_llm_client()
    prompt_text = LLM_AESTHETIC_EVAL()
    model_name = get_default_model()
    
    messages = [
        {"role": "user", "content": [{"type": "text", "text": prompt_text}]}
    ]
    
    for img_path in image_paths[:6]:
        try:
            with open(img_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                mime = "image/png" if img_path.lower().endswith('.png') else "image/jpeg"
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                })
        except Exception as e:
            print(f"[VALIDATION] Warning: skipped loading image {img_path} for VLM: {e}")

    t0 = time.perf_counter()
    raw_response = ""
    try:
        resp = client.chat.completions.create(model=model_name, messages=messages)
        raw_response = resp.choices[0].message.content.strip()
    except Exception as e:
        duration = int((time.perf_counter() - t0) * 1000)
        raise LLMError(
            call_id="vlm_aesthetic_eval",
            model=model_name,
            error_type="api_error",
            error_message=f"API call failed: {str(e)}",
            prompt=prompt_text + " [+ attached images]",
            raw_response="",
            duration_ms=duration
        )

    try:
        # Strict cast - no regex recovery. If LLM added a preamble or refused, this fails.
        val = float(raw_response)
        duration = int((time.perf_counter() - t0) * 1000)
        return val, duration
    except ValueError:
        duration = int((time.perf_counter() - t0) * 1000)
        raise LLMError(
            call_id="vlm_aesthetic_eval",
            model=model_name,
            error_type="format_error",
            error_message="VLM did not return a clean raw float number.",
            prompt=prompt_text + " [+ attached images]",
            raw_response=raw_response,
            duration_ms=duration
        )

def run_validation_ablation(
    pid: int,
    name: str,
    age: int,
    manual_rating: float,
    image_paths: list[str],
    llm_tier: str,
    llm_body_type: str,
    llm_long_score: int,
    llm_short_score: int,
    ml_pred: dict
):
    """
    Executes the 5 ML ablation paths and appends the final result to scoring_eval.csv.
    Expects ml_pred to be the output of `AestheticScorer.predict_profile(image_paths)`.
    """
    _load_validation_models()
    
    faces_extracted = 0
    ml_svr_early = ""
    ml_svr_late = ""
    ml_evc = ""
    evc_latency = ""
    ml_arcface = ""
    arcface_latency = ""
    vlm_score = ""
    vlm_latency = ""
    
    if isinstance(ml_pred, dict):
        ml_svr_early = ml_pred.get("score") if ml_pred.get("score") is not None else ""
        
        diagnostics = ml_pred.get("diagnostics") or {}
        faces_extracted = diagnostics.get("valid_faces_extracted", 0)
        
        # SVR Late Fusion
        ind_scores = diagnostics.get("individual_photo_scores", {}).values()
        if ind_scores:
            ml_svr_late = round(float(np.mean(list(ind_scores))), 2)
            
        # EVC Logistic Regression
        if _evc_model and ml_svr_early != "" and "profile_vector" in diagnostics:
            try:
                t0_evc = time.perf_counter()
                vec = np.array(diagnostics["profile_vector"])
                probs = _evc_model.predict_proba([vec])[0]
                classes = _evc_model.classes_
                ev = sum(p * c for p, c in zip(probs, classes))
                ml_evc = round(float(ev), 2)
                evc_latency = int((time.perf_counter() - t0_evc) * 1000)
            except Exception as e:
                print(f"[VALIDATION] EVC calculation failed: {e}")

    # ArcFace Extractor & SVR
    if _arcface_model and _arcface_app and image_paths:
        try:
            t0_arc = time.perf_counter()
            vecs = []
            for img_p in image_paths:
                img_cv = cv2.imread(img_p)
                if img_cv is not None:
                    faces = _arcface_app.get(img_cv)
                    if faces:
                        vecs.append(faces[0].normed_embedding)
            if vecs:
                avg_vec = np.mean(vecs, axis=0)
                pred = _arcface_model.predict([avg_vec])[0]
                ml_arcface = round(float(pred), 2)
                arcface_latency = int((time.perf_counter() - t0_arc) * 1000)
        except Exception as e:
            print(f"[VALIDATION] ArcFace calculation failed: {e}")

    # VLM Zero-Shot Strict Call
    if image_paths:
        print("[VALIDATION] Executing strict VLM Zero-Shot call...")
        # Note: Exceptions are NOT caught here, so they cleanly bubble up to `start.py`
        vlm_score, vlm_latency = _run_vlm_zero_shot(image_paths)

    # Append to CSV
    file_exists = os.path.isfile(CSV_PATH)
    try:
        with open(CSV_PATH, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "Timestamp", "Profile_ID", "Name", "Age",
                    "faces_extracted", "ml_svr_early", "ml_svr_late",
                    "ml_evc", "evc_latency_ms", "ml_arcface", "arcface_latency_ms", "vlm_zero_shot", "vlm_latency_ms",
                    "LLM_Tier", "LLM_Body_Type", "LLM_Long_Score", "LLM_Short_Score",
                    "manual_rating"
                ])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                pid, name, age,
                faces_extracted,
                ml_svr_early,
                ml_svr_late,
                ml_evc, evc_latency,
                ml_arcface, arcface_latency,
                vlm_score, vlm_latency,
                llm_tier if llm_tier is not None else "",
                llm_body_type if llm_body_type is not None else "",
                llm_long_score,
                llm_short_score,
                manual_rating if manual_rating is not None else ""
            ])
        print(f"[VALIDATION] Successfully logged evaluation metrics for {name} (ID: {pid})")
    except Exception as e:
        print(f"[VALIDATION] Failed to write to CSV: {e}")
