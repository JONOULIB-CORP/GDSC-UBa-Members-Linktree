import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
import os

def train_sut():
    """
    Trains the System Under Test (SUT) using the Kaggle dataset.
    This is the model we will later try to "break" with our testing framework.
    """
    KAGGE_PATH = "ccfd_framework/data/creditcard.csv"
    if not os.path.exists(KAGGE_PATH):
        print("ERROR: Kaggle file missing.")
        return

    print("Loading Kaggle data for SUT training...")
    df = pd.read_csv(KAGGE_PATH)

    # We use all V1-V28 features + Amount
    features = [f'V{i}' for i in range(1, 29)] + ['Amount']
    X = df[features]
    y = df['Class'] # 1=Fraud, 0=Normal

    print("Training Random Forest Fraud Detector (SUT)...")
    # Using a small subset for speed in this demo, but should use more for thesis
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.8, random_state=42, stratify=y)

    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_train, y_train)

    os.makedirs("ccfd_framework/models", exist_ok=True)
    joblib.dump(clf, "ccfd_framework/models/sut_model.pkl")
    print("SUT trained and saved to models/sut_model.pkl")

if __name__ == "__main__":
    train_sut()
