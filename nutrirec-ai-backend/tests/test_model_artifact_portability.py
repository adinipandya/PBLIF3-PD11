import json
import shutil
from pathlib import Path

from scripts import demo_ml_exploratory as demo

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "data/experiments/survey-v001/ml-eval-exploratory-001"
SPLIT = ROOT / "data/experiments/survey-v001/features-exploratory-split-002"


def test_legacy_absolute_and_new_relative_split_paths_resolve_locally(tmp_path):
    model_dir = tmp_path / "data/experiments/survey-v001/ml-eval-exploratory-001"
    local_split = model_dir.parent / "features-exploratory-split-002"
    local_split.mkdir(parents=True)

    legacy_path = (
        "/Users/old-developer/PBLIF3-PD11/data/experiments/survey-v001/"
        "features-exploratory-split-002"
    )
    assert demo._resolve_source_split(model_dir, legacy_path) == local_split.resolve()
    assert demo._resolve_source_split(
        model_dir, "features-exploratory-split-002"
    ) == local_split.resolve()


def test_saved_model_loads_with_legacy_path_from_another_machine(tmp_path):
    model_dir = tmp_path / "data/experiments/survey-v001/ml-eval-exploratory-001"
    split_dir = model_dir.parent / SPLIT.name
    model_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)

    manifest = json.loads((EXPERIMENT / "manifest.json").read_text(encoding="utf-8"))
    manifest["source_split"] = (
        "/Users/previous-owner/PBLIF3-PD11/data/experiments/survey-v001/"
        "features-exploratory-split-002"
    )
    (model_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copy2(EXPERIMENT / "experiment_config.json", model_dir)
    shutil.copy2(EXPERIMENT / "random-forest-exploratory.joblib", model_dir)
    for filename in ("manifest.json", "feature_schema.json"):
        shutil.copy2(SPLIT / filename, split_dir)

    _, _, config, model = demo._load_model_context(model_dir, "Random Forest")

    assert config["source_run_id"] == "pd11-r2-cleanup-003"
    assert hasattr(model, "predict")
    assert hasattr(model, "predict_proba")
