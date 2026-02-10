import numpy as np
import pandas as pd
import joblib
from optimizer import GeneticOptimizer
from test_generator import TestGenerator
from ccfd_system import MockCCFD
import matplotlib.pyplot as plt
import os

class BuggyCCFD(MockCCFD):
    def predict(self, sequence):
        preds = super().predict(sequence)
        # Introduce a bug: If amount is > 800, it fails to detect fraud (returns 0)
        # This is a classic "overflow" or "threshold" bug.
        df = pd.DataFrame(sequence)
        bug_mask = (df['Amount'] > 800)
        preds[bug_mask] = 0
        return preds

def run_evaluation():
    print("Starting Evaluation...")
    n_runs = 50
    results = []

    generator = TestGenerator()
    sut = BuggyCCFD()

    # 1. Random Testing
    print("Running Random Testing...")
    random_violations = 0
    for _ in range(n_runs):
        seq = [{"Amount": np.random.uniform(1, 1500), "TxType": "N/A"} for _ in range(10)]
        orig_pred = sut.predict(seq)
        # Apply MR1
        mod_seq = [tx.copy() for tx in seq]
        for tx in mod_seq: tx['Amount'] *= 1.5
        mod_pred = sut.predict(mod_seq)
        random_violations += np.sum((orig_pred == 1) & (mod_pred == 0))

    # 2. FSM-Based Testing
    print("Running FSM-Based Testing...")
    fsm_violations = 0
    for _ in range(n_runs):
        seq = generator.generate_sequence(profile=0, length=10)
        orig_pred = sut.predict(seq)
        mod_seq = generator.apply_metamorphic_relation(seq, "MR1")
        mod_pred = sut.predict(mod_seq)
        fsm_violations += np.sum((orig_pred == 1) & (mod_pred == 0))

    # 3. Hybrid Optimized Testing (Our Framework)
    print("Running Hybrid Optimized Testing...")
    # Use a customized optimizer for evaluation
    optimizer = GeneticOptimizer(profile=0, pop_size=50, n_generations=20, sut=sut)
    best_seq = optimizer.optimize()
    # Test the best sequence multiple times to account for randomness in BuggyCCFD
    hybrid_violations = 0
    for _ in range(n_runs):
        orig_pred = sut.predict(best_seq)
        mod_seq = generator.apply_metamorphic_relation(best_seq, "MR1")
        mod_pred = sut.predict(mod_seq)
        hybrid_violations += np.sum((orig_pred == 1) & (mod_pred == 0))

    print(f"\nResults over {n_runs} runs:")
    print(f"Random Testing Violations: {random_violations}")
    print(f"FSM-Based Testing Violations: {fsm_violations}")
    print(f"Hybrid Optimized Violations: {hybrid_violations}")

    # Plotting
    methods = ['Random', 'FSM', 'Hybrid (GA)']
    violations = [random_violations, fsm_violations, hybrid_violations]

    plt.figure(figsize=(10, 6))
    plt.bar(methods, violations, color=['gray', 'blue', 'green'])
    plt.ylabel('Nombre de violations MR détectées')
    plt.title('Comparaison des méthodes de test pour CCFD')
    os.makedirs("results", exist_ok=True)
    plt.savefig("results/evaluation_comparison.png")
    print("\nEvaluation plot saved in results/evaluation_comparison.png")

if __name__ == "__main__":
    run_evaluation()
