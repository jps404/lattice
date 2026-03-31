"""Bill passage prediction using logistic regression.

Features used:
- Sponsor party (majority/minority)
- Number of co-sponsors
- Bill body (House/Senate)
- Policy area (one-hot encoded)
- Controversy score from AI analysis
- Sponsor's total campaign donations
- Whether bill has bipartisan sponsors
- Session progress (early vs late introduction)

Trains on historical Louisiana session data, predicts on current session.
Tracks accuracy with Brier score.
"""

import json
import logging
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

from ingestion.db import get_connection, get_cursor

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "predictor_model.pkl")

POLICY_AREAS = [
    "healthcare", "education", "energy", "environment", "criminal_justice",
    "taxation", "housing", "labor", "technology", "transportation",
    "agriculture", "other",
]

# Louisiana House has R majority — adjust per session
MAJORITY_PARTY = "R"


def extract_features(bill_id: int) -> dict | None:
    """Extract prediction features for a single bill."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)

        # Get bill + analysis
        cur.execute(
            """
            SELECT b.*, ba.policy_area, ba.controversy_score
            FROM bills b
            LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
            WHERE b.id = %s
            """,
            (bill_id,),
        )
        bill = cur.fetchone()
        if not bill:
            return None

        # Get sponsor info
        cur.execute(
            """
            SELECT l.party, l.role, COUNT(DISTINCT s2.legislator_id) as cosponsor_count
            FROM sponsorships s
            JOIN legislators l ON l.id = s.legislator_id
            LEFT JOIN sponsorships s2 ON s2.bill_id = s.bill_id AND s2.sponsor_type = 'Co-Sponsor'
            WHERE s.bill_id = %s AND s.sponsor_type = 'Primary'
            GROUP BY l.party, l.role
            """,
            (bill_id,),
        )
        sponsor = cur.fetchone()

        # Check bipartisan support
        cur.execute(
            """
            SELECT COUNT(DISTINCT l.party) as party_count
            FROM sponsorships s
            JOIN legislators l ON l.id = s.legislator_id
            WHERE s.bill_id = %s
            """,
            (bill_id,),
        )
        party_row = cur.fetchone()
        bipartisan = (party_row["party_count"] if party_row else 0) > 1

        # Get sponsor's total donations
        cur.execute(
            """
            SELECT COALESCE(SUM(c.amount), 0) as total_donations
            FROM contributions c
            JOIN sponsorships s ON s.legislator_id = c.legislator_id
            WHERE s.bill_id = %s AND s.sponsor_type = 'Primary'
            """,
            (bill_id,),
        )
        donations = cur.fetchone()

        features = {
            "bill_id": bill_id,
            "is_house": 1 if bill.get("body") == "House" else 0,
            "is_majority_party": 1 if (sponsor and sponsor.get("party") == MAJORITY_PARTY) else 0,
            "cosponsor_count": sponsor["cosponsor_count"] if sponsor else 0,
            "bipartisan": 1 if bipartisan else 0,
            "controversy_score": bill.get("controversy_score") or 0.0,
            "total_sponsor_donations": float(donations["total_donations"]) if donations else 0,
        }

        # One-hot encode policy area
        policy = bill.get("policy_area", "other") or "other"
        for area in POLICY_AREAS:
            features[f"policy_{area}"] = 1 if policy == area else 0

        return features

    finally:
        conn.close()


def build_training_data() -> tuple[pd.DataFrame, pd.Series]:
    """Build training data from historical sessions with known outcomes.

    Uses bills that have reached a terminal status (Passed, Failed, Vetoed).
    """
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT b.id FROM bills b
            LEFT JOIN bill_analyses ba ON ba.bill_id = b.id
            WHERE b.current_status IN ('Passed', 'Failed', 'Vetoed', 'Enrolled')
            """
        )
        bill_ids = [row["id"] for row in cur.fetchall()]
    finally:
        conn.close()

    if not bill_ids:
        raise ValueError("No bills with resolved outcomes found for training")

    rows = []
    labels = []

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        for bill_id in bill_ids:
            features = extract_features(bill_id)
            if features:
                cur.execute("SELECT current_status FROM bills WHERE id = %s", (bill_id,))
                bill = cur.fetchone()
                passed = bill["current_status"] in ("Passed", "Enrolled")
                rows.append(features)
                labels.append(1 if passed else 0)
    finally:
        conn.close()

    df = pd.DataFrame(rows)
    feature_cols = [c for c in df.columns if c != "bill_id"]
    return df[feature_cols], pd.Series(labels)


def train_model() -> dict:
    """Train the passage prediction model on historical data.

    Returns training metrics.
    """
    logger.info("Building training data...")
    X, y = build_training_data()
    logger.info("Training on %d bills (%d passed, %d failed)", len(y), y.sum(), len(y) - y.sum())

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train logistic regression
    model = LogisticRegression(max_iter=1000, random_state=42)

    # Cross-validate
    cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="accuracy")
    brier_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="neg_brier_score")

    # Fit final model on all data
    model.fit(X_scaled, y)

    # Feature importance
    feature_names = list(X.columns)
    importance = dict(zip(feature_names, model.coef_[0].tolist()))

    # Save model
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler, "features": feature_names}, f)

    metrics = {
        "training_samples": len(y),
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
        "cv_brier_mean": float(-brier_scores.mean()),
        "feature_importance": importance,
    }

    logger.info("Model trained. CV accuracy: %.3f (+/- %.3f)", cv_scores.mean(), cv_scores.std())
    return metrics


def predict_bill(bill_id: int) -> float | None:
    """Predict passage probability for a single bill.

    Returns probability (0.0-1.0) or None if prediction fails.
    """
    if not os.path.exists(MODEL_PATH):
        logger.error("No trained model found. Run train_model() first.")
        return None

    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)

    model = saved["model"]
    scaler = saved["scaler"]
    feature_names = saved["features"]

    features = extract_features(bill_id)
    if not features:
        return None

    # Build feature vector in correct order
    X = pd.DataFrame([{k: features.get(k, 0) for k in feature_names}])
    X_scaled = scaler.transform(X)

    prob = model.predict_proba(X_scaled)[0][1]
    return float(prob)


def predict_all_bills() -> dict:
    """Generate predictions for all unresolved bills and store in database."""
    if not os.path.exists(MODEL_PATH):
        logger.error("No trained model. Run train_model() first.")
        return {"error": "no_model"}

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        # Get bills that are still active (not passed/failed)
        cur.execute(
            """
            SELECT b.id FROM bills b
            JOIN bill_analyses ba ON ba.bill_id = b.id
            WHERE b.current_status NOT IN ('Passed', 'Failed', 'Vetoed', 'Enrolled')
            """
        )
        bill_ids = [row["id"] for row in cur.fetchall()]
    finally:
        conn.close()

    logger.info("Predicting for %d active bills", len(bill_ids))
    stats = {"predicted": 0, "skipped": 0}

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        for bill_id in bill_ids:
            prob = predict_bill(bill_id)
            if prob is not None:
                features = extract_features(bill_id)
                cur.execute(
                    """INSERT INTO predictions (bill_id, pass_probability, features, model_version)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (bill_id) DO UPDATE SET
                        pass_probability = EXCLUDED.pass_probability,
                        features = EXCLUDED.features,
                        model_version = EXCLUDED.model_version,
                        predicted_at = NOW()""",
                    (bill_id, prob, json.dumps(features, default=str), "v0.1"),
                )
                stats["predicted"] += 1
            else:
                stats["skipped"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return stats


def update_outcomes() -> dict:
    """Update predictions with actual outcomes for resolved bills."""
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            UPDATE predictions p
            SET actual_outcome = b.current_status,
                resolved_at = NOW()
            FROM bills b
            WHERE p.bill_id = b.id
              AND p.actual_outcome IS NULL
              AND b.current_status IN ('Passed', 'Failed', 'Vetoed', 'Enrolled')
            RETURNING p.id
            """
        )
        updated = len(cur.fetchall())
        conn.commit()
    finally:
        conn.close()

    return {"outcomes_updated": updated}


def calculate_brier_score() -> float | None:
    """Calculate Brier score on resolved predictions.

    Brier score: mean squared error between predicted probabilities and outcomes.
    Lower is better. 0 = perfect, 0.25 = random baseline.
    """
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """
            SELECT pass_probability, actual_outcome
            FROM predictions
            WHERE actual_outcome IS NOT NULL
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    total = 0
    for row in rows:
        actual = 1.0 if row["actual_outcome"] in ("Passed", "Enrolled") else 0.0
        total += (row["pass_probability"] - actual) ** 2

    return total / len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true", help="Train the model")
    parser.add_argument("--predict", action="store_true", help="Predict all active bills")
    parser.add_argument("--brier", action="store_true", help="Calculate Brier score")
    args = parser.parse_args()

    if args.train:
        metrics = train_model()
        print(json.dumps(metrics, indent=2))
    elif args.predict:
        stats = predict_all_bills()
        print(f"Predictions: {stats}")
    elif args.brier:
        score = calculate_brier_score()
        print(f"Brier score: {score}" if score else "No resolved predictions yet")
    else:
        parser.print_help()
