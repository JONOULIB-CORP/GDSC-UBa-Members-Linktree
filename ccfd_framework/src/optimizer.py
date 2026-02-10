import numpy as np
import pandas as pd
import joblib
import copy
from test_generator import TestGenerator
from ccfd_system import MockCCFD

class GeneticOptimizer:
    def __init__(self, profile=0, pop_size=20, n_generations=10, sut=None):
        self.profile = profile
        self.pop_size = pop_size
        self.n_generations = n_generations
        self.generator = TestGenerator()
        self.sut = sut if sut else MockCCFD()

    def fitness(self, sequence):
        # MR1: Increase amount. Expected: If original is fraud, modified MUST be fraud.
        # Violation if original=Fraud and modified=Normal.
        # Or more generally, if original=Normal and modified=Normal but score decreases?
        # Let's keep it simple: count classification changes that are illogical.

        orig_pred = self.sut.predict(sequence)

        # Apply MR1
        mod_sequence = self.generator.apply_metamorphic_relation(sequence, "MR1")
        mod_pred = self.sut.predict(mod_sequence)

        # Count violations: orig=1 (Fraud), mod=0 (Normal) -> Bug!
        violations = np.sum((orig_pred == 1) & (mod_pred == 0))

        # Also reward diversity/coverage (unique states visited)
        coverage = len(set([tx['TxType'] for tx in sequence]))

        return violations * 10 + coverage

    def optimize(self):
        # Initialize population
        population = [self.generator.generate_sequence(self.profile, length=10) for _ in range(self.pop_size)]

        for gen in range(self.n_generations):
            scores = [self.fitness(ind) for ind in population]
            print(f"Gen {gen}: Max Fitness = {max(scores)}")

            # Selection (Top 50%)
            sorted_indices = np.argsort(scores)[::-1]
            population = [population[i] for i in sorted_indices[:self.pop_size//2]]

            # Crossover & Mutation to refill population
            new_pop = [copy.deepcopy(population[0])] # Elitism: keep best
            while len(new_pop) < self.pop_size:
                parent1, parent2 = np.random.choice(len(population), 2, replace=False)
                # Crossover
                split = len(population[parent1]) // 2
                child = copy.deepcopy(population[parent1][:split] + population[parent2][split:])
                # Mutation (Randomly change a transaction)
                if np.random.random() < 0.3:
                    idx = np.random.randint(0, len(child))
                    # Allow mutation to explore much higher amounts (fuzzing)
                    child[idx]['Amount'] *= np.random.uniform(0.1, 5.0)
                new_pop.append(child)
            population = new_pop

        best_idx = np.argmax([self.fitness(ind) for ind in population])
        return population[best_idx]

if __name__ == "__main__":
    optimizer = GeneticOptimizer(profile=0)
    best_test_case = optimizer.optimize()
    print("\nBest Test Case found:")
    for tx in best_test_case:
        print(tx)
