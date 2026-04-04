# CCFD Hybrid Testing Framework (Validation & Verification Tool)

This project implements the framework proposed in the thesis: **"Hybrid Metamorphic and Model Based Event Driven Testing Framework for Credit Card Fraud Detection Systems"**.

**IMPORTANT**: This is a **Testing Framework**, not a fraud detection technique. Its goal is to evaluate, validate, and find "logic holes" in existing fraud detection systems (the "System Under Test" or SUT).

## Project Structure
- `src/`: Core logic for behavioral modeling, metamorphic testing, and genetic optimization.
- `data/`: Placeholder for the Kaggle `creditcard.csv` dataset.
- `models/`: Storage for inferred FSMs and trained SUT models.
- `article/`: LaTeX source for the research article (JSS format).
- `results/`: Output graphs and violation reports.

## Core Concepts
1. **Behavioral Modeling**: We don't just look at one transaction; we look at sequences (FSM) to understand the "context" of a user.
2. **Metamorphic Testing**: We use logical rules (e.g., Monotonicity) to check if the system is consistent, even without a label.
3. **Genetic Optimization**: We use evolutionary search to find the exact sequences that "break" the fraud detector's logic.

## Setup & Execution
1. Place `creditcard.csv` in `ccfd_framework/data/`.
2. Run the master demo script:
   ```bash
   python3 run_thesis_demo.py
   ```
