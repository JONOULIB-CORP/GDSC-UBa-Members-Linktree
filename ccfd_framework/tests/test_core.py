import unittest
import os
import sys
sys.path.append('ccfd_framework/src')
from data_generator import generate_mock_data
from behavioral_model import BehavioralModel
from test_generator import TestGenerator
from ccfd_system import MockCCFD
import pandas as pd

class TestCCFDFramework(unittest.TestCase):
    def test_data_generation(self):
        generate_mock_data(n_users=10, n_transactions=100)
        self.assertTrue(os.path.exists("data/mock_transactions.csv"))
        df = pd.read_csv("data/mock_transactions.csv")
        self.assertEqual(len(df), 100)

    def test_model_training(self):
        df = pd.read_csv("data/mock_transactions.csv", parse_dates=['Timestamp'])
        model = BehavioralModel(n_clusters=2)
        user_features = model.train(df)
        self.assertIn('Profile', user_features.columns)
        fsm = model.build_fsm(df, user_features)
        self.assertEqual(len(fsm), 2)
        # Save for next test
        import joblib
        os.makedirs("models", exist_ok=True)
        joblib.dump(fsm, "models/fsm_model.pkl")

    def test_test_generation(self):
        generator = TestGenerator()
        seq = generator.generate_sequence(profile=0, length=5)
        self.assertEqual(len(seq), 5)
        mr_seq = generator.apply_metamorphic_relation(seq, "MR1")
        self.assertEqual(len(mr_seq), 5)

if __name__ == "__main__":
    unittest.main()
