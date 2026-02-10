import numpy as np
import joblib
import copy

class TestGenerator:
    """
    Phase 2: Creating the Test Suite via Mutation and Metamorphic Relations.
    """
    def __init__(self):
        try:
            self.fsm = joblib.load("ccfd_framework/models/fsm_rules.pkl")
            self.states = ['Low', 'Medium', 'High']
        except:
            self.fsm = None

    def generate_raw_sequence(self, profile=0, length=5):
        """Generates a sequence of transactions based on FSM probabilities."""
        if self.fsm is None: return []

        matrix = self.fsm[profile]
        curr = np.random.choice(self.states)
        seq = []
        for _ in range(length):
            # Simulate a feature vector (Simplified for demo)
            # In a real setup, we would sample from the original Kaggle distribution for that state
            val = {"Amount": 50.0 if curr == 'Medium' else (10.0 if curr == 'Low' else 500.0)}
            # Add dummy V1-V28
            for i in range(1, 29): val[f'V{i}'] = np.random.normal(0, 1)
            seq.append(val)

            # Next state
            probs = matrix.loc[curr].values
            curr = np.random.choice(matrix.columns, p=probs)
        return seq

    def apply_mr1(self, sequence):
        """
        Metamorphic Relation 1: Monotonicity of Amount.
        If a transaction is suspicious, increasing the amount MUST NOT make it less suspicious.
        """
        mutant = copy.deepcopy(sequence)
        for tx in mutant:
            tx['Amount'] *= 2.0 # Double the amount
        return mutant
