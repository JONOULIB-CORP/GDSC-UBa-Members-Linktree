import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib
import os

class BehavioralModel:
    def __init__(self, n_clusters=3):
        self.n_clusters = n_clusters
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        self.scaler = StandardScaler()
        self.profiles = None

    def extract_features(self, df):
        # Aggregate features per user
        features = df.groupby('UserID').agg({
            'Amount': ['mean', 'std', 'count', 'max'],
            'Timestamp': lambda x: (x.max() - x.min()).total_seconds() / 3600 # Duration in hours
        })
        features.columns = ['avg_amount', 'std_amount', 'transaction_count', 'max_amount', 'duration_hours']
        features['frequency'] = features['transaction_count'] / (features['duration_hours'] + 1)
        features = features.fillna(0)
        return features

    def train(self, df):
        print("Extracting features for clustering...")
        features = self.extract_features(df)
        scaled_features = self.scaler.fit_transform(features)

        print(f"Clustering users into {self.n_clusters} profiles...")
        self.profiles = self.kmeans.fit_predict(scaled_features)
        features['Profile'] = self.profiles

        # Save model
        os.makedirs("models", exist_ok=True)
        joblib.dump(self.kmeans, "models/kmeans_model.pkl")
        joblib.dump(self.scaler, "models/scaler.pkl")
        return features

    def build_fsm(self, df, user_features):
        # Simplify FSM: States are the profiles.
        # Transitions are between transaction types within a profile.
        # For now, let's say States are (Profile, TransactionType)
        # TransactionType can be 'Low', 'Medium', 'High' based on amount quantiles.

        df = df.merge(user_features[['Profile']], left_on='UserID', right_index=True)

        # Define transaction types
        df['TxType'] = pd.qcut(df['Amount'], 3, labels=['Low', 'Medium', 'High'])

        # Compute transition matrix per profile
        fsm = {}
        for profile in range(self.n_clusters):
            profile_df = df[df['Profile'] == profile]
            transitions = []

            # Sort by user and time to get sequences
            profile_df = profile_df.sort_values(['UserID', 'Timestamp'])
            profile_df['NextTxType'] = profile_df.groupby('UserID')['TxType'].shift(-1)

            # Count transitions
            trans_counts = profile_df.groupby(['TxType', 'NextTxType']).size().unstack(fill_value=0)
            # Normalize to get probabilities
            trans_probs = trans_counts.div(trans_counts.sum(axis=1), axis=0).fillna(0)
            fsm[profile] = trans_probs

        return fsm

if __name__ == "__main__":
    # Test
    from data_generator import generate_mock_data
    if not os.path.exists("data/mock_transactions.csv"):
        generate_mock_data()

    df = pd.read_csv("data/mock_transactions.csv", parse_dates=['Timestamp'])
    model = BehavioralModel(n_clusters=3)
    user_features = model.train(df)
    fsm = model.build_fsm(df, user_features)

    print("\nFSM Transitions for Profile 0:")
    print(fsm[0])

    # Save FSM
    joblib.dump(fsm, "models/fsm_model.pkl")
    print("\nModels saved in models/")
