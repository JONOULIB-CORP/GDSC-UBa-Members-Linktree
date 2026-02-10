import pandas as pd
import numpy as np
import os

def generate_mock_data(n_users=100, n_transactions=10000):
    users = [f"User_{i}" for i in range(n_users)]
    data = []

    for _ in range(n_transactions):
        user = np.random.choice(users)
        # Normal transaction distribution
        amount = np.random.exponential(scale=50) + 1
        timestamp = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.random.randint(0, 3600*24*30), unit='s')

        # Simple fraud logic: very high amount or very high frequency (simulated by random)
        is_fraud = 0
        if amount > 150: # Lowered threshold to see more frauds in training
            is_fraud = 1 if np.random.random() > 0.3 else 0

        data.append({
            "UserID": user,
            "Amount": amount,
            "Timestamp": timestamp,
            "IsFraud": is_fraud
        })

    df = pd.DataFrame(data)
    df = df.sort_values(by=["UserID", "Timestamp"])

    os.makedirs("data", exist_ok=True)
    df.to_csv("data/mock_transactions.csv", index=False)
    print(f"Generated {n_transactions} transactions for {n_users} users in data/mock_transactions.csv")

if __name__ == "__main__":
    generate_mock_data()
