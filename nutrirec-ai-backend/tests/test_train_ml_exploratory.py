import csv
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from scripts import train_ml_exploratory as train

ROOT = Path(__file__).resolve().parents[2]
SPLIT = ROOT / "data/experiments/survey-v001/features-exploratory-split-002"


def test_fixed_split_and_feature_target_contract():
    manifest, schema, train_rows, test_rows, report = train.validate_split(SPLIT)
    assert len(train_rows) == 828 and len(test_rows) == 222
    assert {r["submission_uid"] for r in train_rows}.isdisjoint({r["submission_uid"] for r in test_rows})
    assert {r["evaluation_group_id"] for r in train_rows}.isdisjoint({r["evaluation_group_id"] for r in test_rows})
    assert manifest["source_run_training_flag"] is False
    assert schema["target"] == {"y": "rating asli survei, 1-4"}
    assert "response_id" not in FEATURES_SET()
    assert "timestamp" not in FEATURES_SET()
    assert "rating_asli" not in FEATURES_SET()
    assert "penanda_penilaian" not in FEATURES_SET()
    assert all(r["status_eksploratif"] == "perlu_tinjau" for r in train_rows + test_rows)


def FEATURES_SET():
    return set(train.FEATURES)


def test_preprocessing_fit_on_train_only_and_unknown_categories_are_ignored():
    model = train.make_pipeline("Decision Tree")
    X_train = np.array([
        ["Rendah", "Protein", 0] + [0] * 11 + [100.0, 10.0, 20.0, 5.0],
        ["Sedang", "Karbohidrat", 1] + [1] + [0] * 10 + [300.0, 20.0, 40.0, 8.0],
        ["Rendah", "Protein", 0] + [0] * 11 + [200.0, 15.0, 30.0, 6.0],
    ], dtype=object)
    y = np.array([2, 3, 4])
    model.fit(X_train, y)
    train_categories = model.named_steps["preprocess"].named_transformers_["categorical"].named_steps["encoder"].categories_
    X_test = np.array([["Kategori-test-saja", "Prioritas-test-saja", 0] + [0] * 11 + [150.0, 12.0, 25.0, 5.0]], dtype=object)
    pred = model.predict(X_test)
    assert len(pred) == 1
    assert "Kategori-test-saja" not in train_categories[0]
    assert "Prioritas-test-saja" not in train_categories[1]


def test_probability_alignment_and_pipeline_roundtrip():
    model = train.make_pipeline("Dummy")
    X = np.array([["Rendah", "Protein", 0] + [0] * 11 + [100.0, 10.0, 20.0, 5.0]] * 4, dtype=object)
    y = np.array([2, 2, 3, 4])
    model.fit(X, y)
    aligned = train.class_probabilities(model, X[:2])
    assert aligned.shape == (2, 4)
    assert np.allclose(aligned.sum(axis=1), 1.0)
    assert np.allclose(aligned[:, 0], 0.0)
    assert model.predict(X[:2]).tolist() == [2, 2]


def test_unknown_holdout_category_pipeline_fits_and_predicts():
    model = train.make_pipeline("KNN")
    X_train = np.array([["Rendah", "Protein", 0] + [0] * 11 + [float(i + 100), 10.0, 20.0, 5.0] for i in range(8)], dtype=object)
    y = np.array([2, 3, 4, 3, 2, 4, 3, 2])
    model.fit(X_train, y)
    X_test = np.array([["TestOnly", "NewPriority", 0] + [0] * 11 + [150.0, 12.0, 22.0, 6.0]], dtype=object)
    assert model.predict(X_test).shape == (1,)
