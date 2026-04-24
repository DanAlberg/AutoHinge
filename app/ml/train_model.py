import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import Ridge
from sklearn.svm import SVR
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

# Constants
EMBEDDINGS_PATH = os.path.join("ml", "profile_embeddings.npy")
LABELS_PATH = os.path.join("ml", "labels.csv")
MODEL_OUTPUT_PATH = os.path.join("ml", "aesthetic_scorer.pkl")

def train_and_evaluate():
    if not os.path.exists(EMBEDDINGS_PATH) or not os.path.exists(LABELS_PATH):
        print("Error: Could not find embeddings or labels file. Ensure you have run embed_faces.py and completed labelling.")
        return

    # Load Data
    print("Loading data...")
    embeddings_dict = np.load(EMBEDDINGS_PATH, allow_pickle=True).item()
    labels_df = pd.read_csv(LABELS_PATH)

    # Filter out empty labels
    labels_df = labels_df.dropna(subset=['score'])

    X = []
    y = []

    # Map labels to embeddings
    for _, row in labels_df.iterrows():
        folder_name = str(row['folder_name'])
        # Try to clean score if it's a string, just taking the numeric part
        try:
            score = float(str(row['score']).strip())
        except ValueError:
            continue
            
        if folder_name in embeddings_dict:
            embedding = embeddings_dict[folder_name].flatten()  # Ensure 1D (512,)
            X.append(embedding)
            y.append(score)

    if not X:
        print("Error: No matching profiles found between labels.csv and profile_embeddings.npy.")
        return

    X = np.array(X)
    y = np.array(y)
    
    print(f"Successfully loaded {len(y)} labeled profiles.")
    
    # Check class balance
    unique, counts = np.unique(y, return_counts=True)
    balance_str = ", ".join([f"Score {u}: {c}" for u, c in zip(unique, counts)])
    print(f"Class Balance: {balance_str}")

    # --- Phase 1: 80/20 Train/Test Split ---
    print("\n--- Performing 80/20 Train/Test Split ---")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
    
    # We use Ridge regression. Alpha controls regularization (preventing overfitting on small datasets)
    # split_model = Ridge(alpha=10.0)
    
    # Testing Support Vector Regressor (SVR)
    split_model = SVR(kernel='rbf', C=1.0, epsilon=0.1)
    split_model.fit(X_train, y_train)

    y_train_pred = split_model.predict(X_train)
    y_test_pred = split_model.predict(X_test)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    test_r2 = r2_score(y_test, y_test_pred)

    print(f"Training Set MAE: {train_mae:.3f}")
    print(f"Testing Set MAE:  {test_mae:.3f}")
    print(f"Testing Set R^2:  {test_r2:.3f}")
    
    if test_mae < 0.6:
        print("-> EXCELLENT: Model predictions are, on average, within 0.6 points of your true rating.")
    elif test_mae < 1.0:
        print("-> GOOD: Model predictions are, on average, within 1.0 point of your true rating.")
    else:
        print("-> POOR: Model is struggling. Consider re-labeling, checking for imbalanced 5s, or using a non-linear model.")

    # --- Phase 2: 100% Retraining ---
    print("\n--- Retraining Final Model on 100% of Data ---")
    # final_model = Ridge(alpha=10.0)
    
    # Testing Support Vector Regressor (SVR)
    final_model = SVR(kernel='rbf', C=1.0, epsilon=0.1)
    final_model.fit(X, y)
    
    final_mae = mean_absolute_error(y, final_model.predict(X))
    print(f"Final 100% Model MAE: {final_mae:.3f}")

    # Save the model
    joblib.dump(final_model, MODEL_OUTPUT_PATH)
    print(f"Final model successfully saved to '{MODEL_OUTPUT_PATH}'")
    print("This `.pkl` file can now be loaded directly into your main app pipeline for live scoring!")

if __name__ == "__main__":
    train_and_evaluate()