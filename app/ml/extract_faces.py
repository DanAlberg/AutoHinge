import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import shutil

# Constants
LOGS_DIR = os.path.join("app", "logs")
OUTPUT_DIR = os.path.join("app", "ml", "processed_faces")
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg')
MARGIN_TOP_PERCENT = 0.60    # 60% margin to catch high hair
MARGIN_BOTTOM_PERCENT = 0.35 # 35% margin to catch chin/neck
MARGIN_SIDE_PERCENT = 0.45   # 45% margin to catch ears/full hair width
MODEL_PATH_FULL = os.path.join("app", "ml", "blaze_face_full_range.tflite")
MODEL_PATH_SHORT = os.path.join("app", "ml", "blaze_face_short_range.tflite")
CONFIDENCE_THRESHOLD = 0.7

def setup_face_detectors():
    if not os.path.exists(MODEL_PATH_FULL):
        print(f"Error: Full range model not found at {MODEL_PATH_FULL}")
        return None, None
    if not os.path.exists(MODEL_PATH_SHORT):
        print(f"Error: Short range model not found at {MODEL_PATH_SHORT}")
        return None, None

    # Setup Full Range Detector
    base_options_full = python.BaseOptions(model_asset_path=MODEL_PATH_FULL)
    options_full = vision.FaceDetectorOptions(base_options=base_options_full, min_detection_confidence=CONFIDENCE_THRESHOLD)
    detector_full = vision.FaceDetector.create_from_options(options_full)

    # Setup Short Range Detector
    base_options_short = python.BaseOptions(model_asset_path=MODEL_PATH_SHORT)
    options_short = vision.FaceDetectorOptions(base_options=base_options_short, min_detection_confidence=CONFIDENCE_THRESHOLD)
    detector_short = vision.FaceDetector.create_from_options(options_short)

    return detector_full, detector_short

def get_image_files(profile_path):
    files = []
    if not os.path.exists(profile_path):
        return files
    for f in os.listdir(profile_path):
        if f.lower().endswith(SUPPORTED_EXTENSIONS):
            files.append(os.path.join(profile_path, f))
    return files

def process_all_images():
    print(f"Starting Face Extraction for all profiles in {LOGS_DIR}...")
    
    if not os.path.exists(LOGS_DIR):
        print(f"Error: Could not find {LOGS_DIR}. Please run this script from inside AutoHinge/app")
        return

    detector_full, detector_short = setup_face_detectors()
    if detector_full is None or detector_short is None:
        return

    # Create/clear output directory
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Get all profiles
    all_profiles = [d for d in os.listdir(LOGS_DIR) if os.path.isdir(os.path.join(LOGS_DIR, d))]
    
    total_profiles = len(all_profiles)
    profiles_with_faces = 0
    total_faces_extracted = 0
    
    for idx, profile in enumerate(all_profiles):
        profile_path = os.path.join(LOGS_DIR, profile)
        image_files = get_image_files(profile_path)
        
        # We need a directory for this profile in the output folder
        profile_out_dir = os.path.join(OUTPUT_DIR, profile)
        
        extracted_for_profile = 0
        
        for img_path in image_files:
            try:
                # Use numpy to read file bytes to handle Unicode paths that break cv2.imread and mp.Image
                import numpy as np
                with open(img_path, "rb") as stream:
                    bytes_data = bytearray(stream.read())
                numpyarray = np.asarray(bytes_data, dtype=np.uint8)
                img_cv2 = cv2.imdecode(numpyarray, cv2.IMREAD_UNCHANGED)
                
                if img_cv2 is None:
                    continue
                ih, iw, _ = img_cv2.shape
                
                # Convert to mp.Image format
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB))

                # Detect faces with both models
                result_full = detector_full.detect(image)
                result_short = detector_short.detect(image)
                
                valid_full = len(result_full.detections) == 1
                valid_short = len(result_short.detections) == 1
                
                if not valid_full and not valid_short:
                    continue # Neither model found exactly 1 face
                    
                detection = None
                
                # Logic: Pick highest confidence if both valid. 
                # If only one valid, use that one.
                # Prioritize full_range if confidence is perfectly tied.
                if valid_full and valid_short:
                    conf_full = result_full.detections[0].categories[0].score
                    conf_short = result_short.detections[0].categories[0].score
                    
                    if conf_full >= conf_short:
                        detection = result_full.detections[0]
                    else:
                        detection = result_short.detections[0]
                elif valid_full:
                    detection = result_full.detections[0]
                else:
                    detection = result_short.detections[0]
                    
                if detection is None:
                    continue
                bbox = detection.bounding_box
                
                # Absolute coordinates
                x = bbox.origin_x
                y = bbox.origin_y
                w = bbox.width
                h = bbox.height
                
                # Calculate asymmetric margins
                margin_w = int(w * MARGIN_SIDE_PERCENT)
                margin_h_top = int(h * MARGIN_TOP_PERCENT)
                margin_h_bottom = int(h * MARGIN_BOTTOM_PERCENT)
                
                # Calculate padded coordinates
                x1 = max(0, x - margin_w)
                y1 = max(0, y - margin_h_top)
                x2 = min(iw, x + w + margin_w)
                y2 = min(ih, y + h + margin_h_bottom)
                
                # CROP the image array
                crop_img = img_cv2[y1:y2, x1:x2]
                
                # Skip if crop is empty for some reason
                if crop_img.size == 0:
                    continue
                
                # Ensure the profile output directory exists before saving the first face
                if not os.path.exists(profile_out_dir):
                    os.makedirs(profile_out_dir, exist_ok=True)

                # Save the cropped image
                filename = os.path.basename(img_path)
                out_path = os.path.join(profile_out_dir, filename)
                is_success, im_buf_arr = cv2.imencode(".png", crop_img)
                if is_success:
                    im_buf_arr.tofile(out_path)
                
                extracted_for_profile += 1
                total_faces_extracted += 1
                
            except Exception as e:
                # Silently catch errors so one corrupt image doesn't stop the pipeline
                pass
                
        if extracted_for_profile > 0:
            profiles_with_faces += 1
            
        # Simple progress update every 50 profiles
        if (idx + 1) % 50 == 0:
            print(f"Processed {idx + 1}/{total_profiles} profiles...")

    print("\n--- Extraction Complete ---")
    print(f"Total Profiles Processed: {total_profiles}")
    print(f"Profiles with >= 1 valid face: {profiles_with_faces}")
    print(f"Total Cropped Faces Saved: {total_faces_extracted}")
    print(f"Output Directory: {OUTPUT_DIR}")

if __name__ == "__main__":
    process_all_images()