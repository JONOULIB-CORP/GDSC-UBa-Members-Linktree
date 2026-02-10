import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib
import os

class BehavioralModel:
    """
    This class handles Phase 1: Deriving the Behavioral Model from the Kaggle dataset.
    It identifies user profiles and builds transition rules (FSM).
    """
    def __init__(self, n_clusters=3):
        self.n_clusters = n_clusters
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        self.scaler = StandardScaler()

    def load_kaggle_data(self, filepath):
        """Loads the real Kaggle CSV."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Kaggle dataset not found at {filepath}. Please download creditcard.csv from Kaggle.")
        return pd.read_csv(filepath)

    def extract_features(self, df):
        """
        Step 1: Inferring Abstract Behavioral Profiles.
        We group transactions to see patterns. In the real Kaggle set,
        we don't have UserIDs, so we simulate sequences or treat time windows as users.
        For this implementation, we use 'Time' to simulate user sessions.
        """
        # Feature engineering: Time of day, Amount categories
        df['Hour'] = (df['Time'] / 3600) % 24

        # We select PCA features V1-V28 provided by Kaggle + Amount + Hour
        features = df[['V1', 'V2', 'Amount', 'Hour']]
        return features

    def train_profiles(self, df):
        """Step 1 & 2: Clustering and Drift detection (simplified)."""
        print("[1/4] Extracting behavioral features...")
        features = self.extract_features(df)
        scaled = self.scaler.fit_transform(features)

        print(f"[2/4] Clustering into {self.n_clusters} behavioral profiles...")
        df['Profile'] = self.kmeans.fit_predict(scaled)

        os.makedirs("ccfd_framework/models", exist_ok=True)
        joblib.dump(self.kmeans, "ccfd_framework/models/kmeans_model.pkl")
        joblib.dump(self.scaler, "ccfd_framework/models/scaler.pkl")
        return df

    def build_fsm_rules(self, df):
        """Step 3 & 4: Defining FSM States and Transition Rules."""
        print("[3/4] Defining FSM states based on Amount Quantiles...")
        # States (S): Low-Amount, Medium-Amount, High-Amount
        df['State'] = pd.qcut(df['Amount'], 3, labels=['Low', 'Medium', 'High'])

        print("[4/4] Inferring transition probabilities...")
        fsm_map = {}
        for p in range(self.n_clusters):
            pdf = df[df['Profile'] == p].copy()
            # Transitions are based on chronological sequence in the dataset
            pdf['Next_State'] = pdf['State'].shift(-1)
            trans = pd.crosstab(pdf['State'], pdf['Next_State'], normalize='index')
            fsm_map[p] = trans

        joblib.dump(fsm_map, "ccfd_framework/models/fsm_rules.pkl")
        print("Done! Behavioral Model (FSM) saved in models/fsm_rules.pkl")
        return fsm_map

if __name__ == "__main__":
    # If the user hasn't provided the file, we help them
    KAGGE_PATH = "ccfd_framework/data/creditcard.csv"
    model = BehavioralModel()
    try:
        data = model.load_kaggle_data(KAGGE_PATH)
        df_with_profiles = model.train_profiles(data)
        model.build_fsm_rules(df_with_profiles)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("DIRECTIONS: Please place 'creditcard.csv' from Kaggle in ccfd_framework/data/")
