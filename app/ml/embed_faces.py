import os
import torch
import numpy as np
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from tqdm import tqdm

# Constants
PROCESSED_DIR = os.path.join("ml", "processed_faces")
OUTPUT_EMBEDDINGS = os.path.join("ml", "profile_embeddings.npy")
MODEL_ID = "openai/clip-vit-base-patch32"

def get_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def embed_faces():
    print(f"Loading CLIP model '{MODEL_ID}'...")
    device = get_device()
    print(f"Using device: {device}")
    
    # Load CLIP model and processor
    model = CLIPModel.from_pretrained(MODEL_ID).to(device)
    processor = CLIPProcessor.from_pretrained(MODEL_ID)
    
    if not os.path.exists(PROCESSED_DIR):
        print(f"Error: Could not find processed faces directory: {PROCESSED_DIR}")
        return
        
    profiles = [d for d in os.listdir(PROCESSED_DIR) if os.path.isdir(os.path.join(PROCESSED_DIR, d))]
    
    if not profiles:
        print("No profiles found to embed.")
        return
        
    print(f"Found {len(profiles)} profiles. Starting embedding generation...")
    
    profile_embeddings = {}
    
    # Try logic wrapper for clean error handling
    try:
        # Disable gradient calculation for inference
        with torch.no_grad():
            for profile in tqdm(profiles, desc="Processing Profiles"):
                profile_path = os.path.join(PROCESSED_DIR, profile)
                images = []
                
                for f in os.listdir(profile_path):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        img_path = os.path.join(profile_path, f)
                        try:
                            # Open image and convert to RGB
                            img = Image.open(img_path).convert("RGB")
                            images.append(img)
                        except Exception as e:
                            print(f"Error loading {img_path}: {e}")
                            
                if not images:
                    continue
                    
                # Process all images for this profile in one batch
                inputs = processor(images=images, return_tensors="pt").to(device)
                
                # Get image embeddings (shape: [batch_size, 512])
                outputs = model.get_image_features(**inputs)
                
                # Handling modern transformers return type
                if hasattr(outputs, 'image_embeds'):
                    image_features = outputs.image_embeds
                elif hasattr(outputs, 'last_hidden_state'):
                    # Fallback if get_image_features returns Base model output
                    image_features = outputs.last_hidden_state[:, 0, :]
                else:
                    # It's a raw tensor
                    image_features = outputs
                    
                # Normalize the embeddings
                image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
                
                # EARLY FUSION: Average all face embeddings into a single master profile vector
                # shape: [1, 512]
                profile_vector = torch.mean(image_features, dim=0)
                
                # Re-normalize the averaged vector
                profile_vector = profile_vector / profile_vector.norm(p=2, dim=-1, keepdim=True)
                
                # Move to CPU and convert to numpy
                profile_embeddings[profile] = profile_vector.cpu().numpy()
                
        # Save the dictionary of embeddings
        print(f"\nFinished extracting embeddings for {len(profile_embeddings)} profiles.")
        
        # Save securely 
        np.save(OUTPUT_EMBEDDINGS, profile_embeddings)
        print(f"Saved embeddings to {OUTPUT_EMBEDDINGS}")
        
    except Exception as e:
        print(f"\nAn error occurred during embedding: {e}")


if __name__ == "__main__":
    embed_faces()