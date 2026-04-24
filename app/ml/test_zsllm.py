import os
import sys
import base64
import time
import csv
from datetime import datetime

# Inject app directory to sys.path so llm_client can be imported
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import config # load .env explicitly
os.environ.setdefault("LLM_PROVIDER", "gemini")

from llm_client import get_llm_client, get_default_model

# ---------------------------------------------------------
# CONFIGURATION - EDIT THESE VARIABLES FOR YOUR TESTS
# ---------------------------------------------------------

# Target folder containing up to 6 profile images (.png, .jpg)
TARGET_FOLDER = r"C:\Users\danie\Documents\Hinge\AutoHinge\app\logs\20260310_211615_05_Hannah"

# The Zero-Shot prompt to send alongside the images
TEST_PROMPT = (
    "We are testing alignment between LLM visual clarity and general public perception. \n"
    "Rate the subject's visual attractiveness on a continuous scale from 1.0 to 5.0. \n"
    "Use a heteronormative, harsh rating with age weighting (i.e. older individuals naturally score lower). Inflated scores should be avoided. 1 = Severely unattractive, 2 = , 3 = average mid 20s subject, 4 = significantly more attractive than average, etc. \n"
    "There will be a significant penalty for significant deviations from the public scoring - particularly over inflation of scores. Unattractive subjects must be labelled as such based on natural attributes. Smiles, etc. are not enough to elevate someone with an otherwise unattractive face.\n"
    "Right now the testing is showing massive inflation from individuals who the public rate as 1, 2, 3 vs LLM. \n"
    "You MUST output exactly two lines.\n"
    "Line 1: If the score is strictly less than 2.75 or strictly greater than 3.25, provide a concise 1-sentence reasoning for the deviation. Otherwise, leave Line 1 completely blank."
    "Line 2: The raw float score ONLY.\n"
)

# Number of times to ping the API (Used only if RUN_MODE == 1)
NUM_RUNS = 5

# Set RUN_MODE to:
# 1 = Single model pinged NUM_RUNS times (tests model deviation)
# 2 = Ping each of the 5 hardcoded Gemini models once (tests inter-model consensus)
RUN_MODE = 2

# Used only if RUN_MODE == 1
SINGLE_MODEL_TARGET = "gemini-3.1-pro-preview"

# The list of hardcoded models used if RUN_MODE == 2
MODELS_TO_TEST = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

# Where to save the results
OUTPUT_CSV = os.path.join(APP_DIR, "ml", "zsllm_test_results.csv")

# ---------------------------------------------------------

def run_test():
    print(f"=== ZSLLM Standalone Test ===")
    print(f"Target: {TARGET_FOLDER}")
    print(f"Mode: {'1 (Single Model Deviation)' if RUN_MODE == 1 else '2 (Multi-Model Consensus)'}")
    print("-----------------------------\n")

    if not os.path.exists(TARGET_FOLDER) or not os.path.isdir(TARGET_FOLDER):
        print(f"[ERROR] Target folder does not exist: {TARGET_FOLDER}")
        return

    # Gather images
    image_paths = []
    for f in os.listdir(TARGET_FOLDER):
        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
            image_paths.append(os.path.join(TARGET_FOLDER, f))

    if not image_paths:
        print(f"[ERROR] No images found in {TARGET_FOLDER}")
        return

    print(f"Found {len(image_paths)} images. Proceeding with requests...\n")
    client = get_llm_client()
    
    # Initialize CSV if it doesn't exist
    file_exists = os.path.isfile(OUTPUT_CSV)
    
    with open(OUTPUT_CSV, mode='a', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow([
                "Timestamp", "Folder_Name", "Model_Name", "Run_Iteration", 
                "Parsed_Score", "Reasoning", "Latency_ms", "Raw_Response", "Error_Type"
            ])

        folder_name = os.path.basename(TARGET_FOLDER)

        # Setup the execution plan based on RUN_MODE
        execution_plan = []
        if RUN_MODE == 1:
            for i in range(1, NUM_RUNS + 1):
                execution_plan.append({"model": SINGLE_MODEL_TARGET, "iteration": i})
        else:
            for i, model in enumerate(MODELS_TO_TEST, 1):
                execution_plan.append({"model": model, "iteration": 1})

        for run_idx, step in enumerate(execution_plan, 1):
            current_model = step["model"]
            current_iter = step["iteration"]
            
            print(f"Run [{run_idx}/{len(execution_plan)}] -> Model: {current_model}...")
            
            # Construct the payload
            messages = [
                {"role": "user", "content": [{"type": "text", "text": TEST_PROMPT}]}
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
                    print(f"  [Warning] Failed to load image {img_path}: {e}")

            score = ""
            reasoning = ""
            latency = ""
            raw_response = ""
            error_type = ""
            
            t0 = time.perf_counter()
            try:
                resp = client.chat.completions.create(model=current_model, messages=messages)
                latency = int((time.perf_counter() - t0) * 1000)
                raw_response = resp.choices[0].message.content.strip()
                
                # Split by lines
                lines = [line.strip() for line in raw_response.split('\n') if line.strip()]
                
                if not lines:
                    raise ValueError("Empty response received")
                
                # Strict parse line 1
                score = float(lines[0])
                
                # Parse line 2 if it exists
                if len(lines) > 1:
                    reasoning = " ".join(lines[1:])
                
                print(f"  -> Success: Score = {score} | Reasoning = '{reasoning}' (Latency: {latency}ms)")
                
            except Exception as e:
                latency = int((time.perf_counter() - t0) * 1000)
                print(f"  -> [FAILED] {type(e).__name__}: {e}")
                error_type = type(e).__name__
                if raw_response:
                    print(f"     Raw Response was: '{raw_response.replace(chr(10), ' ')}'")
                    if error_type == "ValueError":
                        error_type = "FormatError (Non-Float)"

            # Append result row
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                folder_name,
                current_model,
                current_iter,
                score,
                reasoning,
                latency,
                raw_response.replace('\n', ' | '), # Keep CSV clean but show line breaks
                error_type
            ])
            
            # Sleep slightly to avoid strict rate limiting if hammering API
            if run_idx < len(execution_plan):
                time.sleep(1)

    print(f"\n=== Test Complete ===")
    print(f"Results appended to: {OUTPUT_CSV}")

if __name__ == "__main__":
    run_test()
