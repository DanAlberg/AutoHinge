import os
import cv2
import torch
import numpy as np
import joblib
from PIL import Image
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from transformers import CLIPProcessor, CLIPModel
import warnings
import logging

# Suppress annoying HuggingFace symlink warnings in production output
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
# Suppress transformers logging (e.g. LOAD REPORT tables)
from transformers import logging as hf_logging
hf_logging.set_verbosity_error()
# Suppress MediaPipe C++ GLOG output
os.environ["GLOG_minloglevel"] = "2"

# Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH_FULL = os.path.join(SCRIPT_DIR, "blaze_face_full_range.tflite")
MODEL_PATH_SHORT = os.path.join(SCRIPT_DIR, "blaze_face_short_range.tflite")
SCORER_MODEL_PATH = os.path.join(SCRIPT_DIR, "aesthetic_scorer.pkl")
EMBEDDINGS_PATH = os.path.join(SCRIPT_DIR, "profile_embeddings.npy")
LABELS_PATH = os.path.join(SCRIPT_DIR, "labels.csv")
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"

MARGIN_TOP_PERCENT = 0.60
MARGIN_BOTTOM_PERCENT = 0.35
MARGIN_SIDE_PERCENT = 0.45
CONFIDENCE_THRESHOLD = 0.70

class AestheticScorer:
    def __init__(self):
        """Initializes the entire pipeline (Extractors, Embedder, Regressor, and Diagnostics) into memory."""
        self._load_face_detectors()
        self._load_clip_model()
        self._load_regressor()
        self._load_diagnostic_data()
        
    def _load_face_detectors(self):
        if not os.path.exists(MODEL_PATH_FULL) or not os.path.exists(MODEL_PATH_SHORT):
            raise FileNotFoundError("MediaPipe models missing from ml/ directory.")
            
        base_options_full = python.BaseOptions(model_asset_path=MODEL_PATH_FULL)
        options_full = vision.FaceDetectorOptions(base_options=base_options_full, min_detection_confidence=CONFIDENCE_THRESHOLD)
        self.detector_full = vision.FaceDetector.create_from_options(options_full)

        base_options_short = python.BaseOptions(model_asset_path=MODEL_PATH_SHORT)
        options_short = vision.FaceDetectorOptions(base_options=base_options_short, min_detection_confidence=CONFIDENCE_THRESHOLD)
        self.detector_short = vision.FaceDetector.create_from_options(options_short)

    def _load_clip_model(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.clip_model = CLIPModel.from_pretrained(CLIP_MODEL_ID).to(self.device)
        self.clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)
        self.clip_model.eval()

    def _load_regressor(self):
        if not os.path.exists(SCORER_MODEL_PATH):
            raise FileNotFoundError(f"Trained model not found at {SCORER_MODEL_PATH}")
        self.regressor = joblib.load(SCORER_MODEL_PATH)
        
    def _load_diagnostic_data(self):
        import csv
        self.training_embeddings = {}
        self.training_labels = {}
        
        if os.path.exists(EMBEDDINGS_PATH):
            self.training_embeddings = np.load(EMBEDDINGS_PATH, allow_pickle=True).item()
            
        if os.path.exists(LABELS_PATH):
            with open(LABELS_PATH, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0] != "folder_name":
                        try:
                            self.training_labels[row[0]] = float(row[1])
                        except:
                            pass

    def extract_faces_from_image(self, img_path):
        """Attempts to crop a face from a single image using the dual-model logic."""
        try:
            with open(img_path, "rb") as stream:
                bytes_data = bytearray(stream.read())
            numpyarray = np.asarray(bytes_data, dtype=np.uint8)
            img_cv2 = cv2.imdecode(numpyarray, cv2.IMREAD_UNCHANGED)
            
            if img_cv2 is None:
                return None
                
            ih, iw, _ = img_cv2.shape
            image_mp = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB))

            result_full = self.detector_full.detect(image_mp)
            result_short = self.detector_short.detect(image_mp)
            
            valid_full = len(result_full.detections) == 1
            valid_short = len(result_short.detections) == 1
            
            if not valid_full and not valid_short:
                return None
                
            detection = None
            if valid_full and valid_short:
                conf_full = result_full.detections[0].categories[0].score
                conf_short = result_short.detections[0].categories[0].score
                detection = result_full.detections[0] if conf_full >= conf_short else result_short.detections[0]
            elif valid_full:
                detection = result_full.detections[0]
            else:
                detection = result_short.detections[0]
                
            bbox = detection.bounding_box
            x, y, w, h = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height
            
            margin_w = int(w * MARGIN_SIDE_PERCENT)
            margin_h_top = int(h * MARGIN_TOP_PERCENT)
            margin_h_bottom = int(h * MARGIN_BOTTOM_PERCENT)
            
            x1, y1 = max(0, x - margin_w), max(0, y - margin_h_top)
            x2, y2 = min(iw, x + w + margin_w), min(ih, y + h + margin_h_bottom)
            
            crop_img = img_cv2[y1:y2, x1:x2]
            if crop_img.size == 0:
                return None
                
            # Convert CV2 BGR to PIL RGB for CLIP
            rgb_crop = cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb_crop)
            
        except Exception as e:
            return None

    def predict_profile(self, image_paths):
        """
        Takes a list of file paths (the 6 Hinge photos).
        Returns a dict: {'score': float, 'diagnostics': dict}
        """
        valid_faces = []
        diagnostics = {
            'total_images_provided': len(image_paths),
            'valid_faces_extracted': 0,
            'individual_photo_scores': {},
            'error': None
        }

        # 1. Extract
        for path in image_paths:
            face_img = self.extract_faces_from_image(path)
            if face_img is not None:
                valid_faces.append((os.path.basename(path), face_img))

        diagnostics['valid_faces_extracted'] = len(valid_faces)

        if not valid_faces:
            diagnostics['error'] = "No valid faces found in any provided images."
            return {'score': None, 'diagnostics': diagnostics}

        # 2. Embed & Predict individually for diagnostics
        master_features_list = []
        
        with torch.no_grad():
            for filename, img in valid_faces:
                inputs = self.clip_processor(images=img, return_tensors="pt").to(self.device)
                outputs = self.clip_model.get_image_features(**inputs)
                
                if hasattr(outputs, 'image_embeds'):
                    features = outputs.image_embeds
                elif hasattr(outputs, 'last_hidden_state'):
                    features = outputs.last_hidden_state[:, 0, :]
                else:
                    features = outputs
                    
                # Normalize
                features = features / features.norm(p=2, dim=-1, keepdim=True)
                master_features_list.append(features)
                
                # Predict individual score
                features_np = features.cpu().numpy().flatten()
                ind_score = self.regressor.predict([features_np])[0]
                diagnostics['individual_photo_scores'][filename] = round(float(ind_score), 2)

        # 3. Early Fusion (Average) for final profile score
        stacked_features = torch.cat(master_features_list, dim=0)
        profile_vector = torch.mean(stacked_features, dim=0, keepdim=True)
        profile_vector = profile_vector / profile_vector.norm(p=2, dim=-1, keepdim=True)
        
        profile_vector_np = profile_vector.cpu().numpy().flatten()
        final_score = self.regressor.predict([profile_vector_np])[0]

        # Bound the score between 1 and 5 just in case
        final_score = max(1.0, min(5.0, final_score))
        
        diagnostics['profile_vector'] = profile_vector_np.tolist()
        
        # 4. Find Nearest Neighbors for diagnostic transparency
        diagnostics['similar_profiles'] = []
        if self.training_embeddings and self.training_labels:
            similarities = []
            for known_id, known_vector in self.training_embeddings.items():
                known_vector_np = known_vector.flatten()
                # Cosine similarity between two normalized vectors is just the dot product
                cos_sim = np.dot(profile_vector_np, known_vector_np)
                if known_id in self.training_labels:
                    similarities.append((cos_sim, known_id, self.training_labels[known_id]))
                    
            # Sort descending
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            # Take top 3
            for sim, k_id, k_score in similarities[:3]:
                diagnostics['similar_profiles'].append({
                    'folder': k_id,
                    'similarity': f"{sim * 100:.1f}%",
                    'your_rating': k_score
                })

        return {
            'score': round(float(final_score), 2),
            'diagnostics': diagnostics
        }

# Example Usage
if __name__ == "__main__":
    import sys
    scorer = AestheticScorer()
    
    # Test on a specific folder if provided via CLI
    if len(sys.argv) > 1:
        test_dir = sys.argv[1]
        imgs = [os.path.join(test_dir, f) for f in os.listdir(test_dir) if f.lower().endswith(('.png', '.jpg'))]
        result = scorer.predict_profile(imgs)
        print(f"\nFinal Profile Score: {result['score']}")
        print("Diagnostics:", result['diagnostics'])