import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib
import os

def train_mock_ccfd(data_path="data/mock_transactions.csv"):
    df = pd.read_csv(data_path)
    # Simple feature engineering for the CCFD system
    df['Amount_Log'] = np.log1p(df['Amount'])

    # We don't have many features in mock data, so let's use what we have
    X = df[['Amount', 'Amount_Log']]
    y = df['IsFraud']

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)

    os.makedirs("models", exist_ok=True)
    joblib.dump(clf, "models/ccfd_system.pkl")
    print("Mock CCFD system trained and saved.")
    return clf

class MockCCFD:
    def __init__(self, model_path="models/ccfd_system.pkl"):
        self.model = joblib.load(model_path)

    def predict(self, sequence):
        # Convert sequence to DataFrame
        df = pd.DataFrame(sequence)
        df['Amount_Log'] = np.log1p(df['Amount'])
        X = df[['Amount', 'Amount_Log']]
        return self.model.predict(X)

if __name__ == "__main__":
    import numpy as np
    train_mock_ccfd()
