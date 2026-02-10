import numpy as np
import joblib
import copy
from test_generator import TestGenerator
import pandas as pd

class GeneticOptimizer:
    """
    Phase 3: Genetic Algorithm (GA) Optimization.
    Finds the transaction sequences that most likely "break" the SUT.
    """
    def __init__(self, sut, population_size=10):
        self.sut = sut
        self.pop_size = population_size
        self.gen = TestGenerator()

    def fitness(self, sequence):
        """
        Fitness function: Violations of Metamorphic Relations.
        Goal: Maximize logical contradictions.
        """
        # Original predictions
        df_orig = pd.DataFrame(sequence)
        preds_orig = self.sut.predict(df_orig)

        # Metamorphic predictions
        seq_mr = self.gen.apply_mr1(sequence)
        df_mr = pd.DataFrame(seq_mr)
        preds_mr = self.sut.predict(df_mr)

        # Violation = Original was Fraud (1), but after increasing amount it became Normal (0)
        violations = np.sum((preds_orig == 1) & (preds_mr == 0))
        return violations

    def evolve(self, generations=5):
        """Main GA Loop."""
        # Initial population from FSM
        pop = [self.gen.generate_raw_sequence() for _ in range(self.pop_size)]

        for g in range(generations):
            scores = [self.fitness(ind) for ind in pop]
            print(f"GA Generation {g}: Best Violation Count = {max(scores)}")

            # Selection, Crossover, Mutation...
            # (Simplified for the demo - we keep the best and mutate them)
            best_idx = np.argmax(scores)
            best_parent = pop[best_idx]

            new_pop = [best_parent]
            for _ in range(self.pop_size - 1):
                child = copy.deepcopy(best_parent)
                # Mutation: Randomly shuffle an amount
                idx = np.random.randint(len(child))
                child[idx]['Amount'] *= np.random.uniform(0.5, 2.0)
                new_pop.append(child)
            pop = new_pop
        return pop[0]
