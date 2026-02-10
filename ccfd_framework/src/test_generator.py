import numpy as np
import pandas as pd
import joblib
import copy

class TestGenerator:
    def __init__(self, fsm_path="models/fsm_model.pkl"):
        self.fsm = joblib.load(fsm_path)
        self.tx_types = ['Low', 'Medium', 'High']
        # Amount ranges (approximate from mock data quantiles)
        self.amount_ranges = {
            'Low': (1, 20),
            'Medium': (20, 60),
            'High': (60, 500)
        }

    def generate_sequence(self, profile, length=10):
        matrix = self.fsm[profile]
        current_state = np.random.choice(self.tx_types)
        sequence = []

        for _ in range(length):
            # Pick an amount in the range
            low, high = self.amount_ranges[current_state]
            amount = np.random.uniform(low, high)
            sequence.append({
                "TxType": current_state,
                "Amount": amount
            })

            # Transition
            probs = matrix.loc[current_state].values
            current_state = np.random.choice(self.tx_types, p=probs)

        return sequence

    def apply_metamorphic_relation(self, sequence, relation_type="MR1"):
        modified_sequence = copy.deepcopy(sequence)
        if relation_type == "MR1":
            # Increase amount of a random transaction
            idx = np.random.randint(0, len(modified_sequence))
            modified_sequence[idx]['Amount'] *= 1.5
        return modified_sequence

    def mutate_fsm(self, profile):
        # Create a mutant FSM by shuffling transition probabilities
        mutant_fsm = self.fsm.copy()
        matrix = mutant_fsm[profile].copy()

        for state in self.tx_types:
            probs = matrix.loc[state].values
            np.random.shuffle(probs)
            matrix.loc[state] = probs

        mutant_fsm[profile] = matrix
        return mutant_fsm

if __name__ == "__main__":
    generator = TestGenerator()
    seq = generator.generate_sequence(profile=0, length=5)
    print("Original Sequence:")
    for tx in seq:
        print(tx)

    mr_seq = generator.apply_metamorphic_relation(seq, "MR1")
    print("\nModified Sequence (MR1 - Increased Amount):")
    for tx in mr_seq:
        print(tx)
