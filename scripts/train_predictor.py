"""Train the bill passage prediction model.

Usage:
    uv run python scripts/train_predictor.py
    uv run python scripts/train_predictor.py --predict   # Also generate predictions after training
"""

import argparse
import json
import logging

from analysis.predictor import train_model, predict_all_bills, calculate_brier_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Train LATTICE passage predictor")
    parser.add_argument("--predict", action="store_true", help="Generate predictions after training")
    args = parser.parse_args()

    print("Training passage prediction model...")
    metrics = train_model()

    print(f"\nTraining Results:")
    print(f"  Samples:      {metrics['training_samples']}")
    print(f"  CV Accuracy:  {metrics['cv_accuracy_mean']:.1%} (+/- {metrics['cv_accuracy_std']:.1%})")
    print(f"  Brier Score:  {metrics['cv_brier_mean']:.4f}")
    print(f"\n  Top features:")
    importance = sorted(metrics["feature_importance"].items(), key=lambda x: abs(x[1]), reverse=True)
    for name, coef in importance[:10]:
        direction = "+" if coef > 0 else "-"
        print(f"    {direction} {name}: {coef:.3f}")

    if args.predict:
        print("\nGenerating predictions for active bills...")
        stats = predict_all_bills()
        print(f"  Predicted: {stats.get('predicted', 0)}")
        print(f"  Skipped:   {stats.get('skipped', 0)}")

        brier = calculate_brier_score()
        if brier is not None:
            print(f"  Current Brier score: {brier:.4f}")


if __name__ == "__main__":
    main()
