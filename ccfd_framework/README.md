# CCFD Hybrid Testing Framework

This project implements the framework proposed in the thesis: **"Hybrid Metamorphic and Model Based Event Driven Testing Framework for Credit Card Fraud Detection Systems"**.

## Project Structure
- `src/`: Source code for the framework.
- `data/`: Generated datasets.
- `models/`: Trained models (K-Means, FSM, Target SUT).
- `results/`: Evaluation plots and reports.
- `tests/`: Unit tests for verification.

## Setup
1. Install dependencies:
   ```bash
   pip install pandas numpy scikit-learn joblib matplotlib
   ```

## Execution Flow
Run the scripts in the following order:

1. **Generate Data**:
   ```bash
   python src/data_generator.py
   ```
2. **Train Behavioral Model**:
   ```bash
   python src/behavioral_model.py
   ```
3. **Train Target System (SUT)**:
   ```bash
   python src/ccfd_system.py
   ```
4. **Run Optimization & Evaluation**:
   ```bash
   python src/evaluation.py
   ```

## How it works
- **Behavioral Modeling**: Uses K-Means clustering to identify user profiles and builds a Finite State Machine (FSM) to represent transaction sequences.
- **Metamorphic Testing**: Uses metamorphic relations (MR) to identify logical inconsistencies in the fraud detection system without requiring a ground-truth oracle.
- **Genetic Algorithm**: Evolves transaction sequences to maximize the detection of MR violations.
