"""Prebuilt classifier (reused only while data + scikit-learn match) and startup warm-up."""
import shutil
import time

import sklearn
from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.main import app
from app.pipeline.classify import MODEL_FILE, load_or_train

PROBE = "Outlook keeps asking for my password after the update"


def test_saved_classifier_reused_until_data_or_sklearn_changes(tmp_path, monkeypatch):
    data_dir, index_dir = tmp_path / "data", tmp_path / "index"
    data_dir.mkdir()
    shutil.copy(get_settings().data_dir / "historical_tickets.csv", data_dir)

    first, source = load_or_train(data_dir, index_dir)
    assert source == "trained" and (index_dir / MODEL_FILE).exists()

    again, source = load_or_train(data_dir, index_dir)
    assert source == "loaded"
    assert again.predict(PROBE) == first.predict(PROBE)  # the saved model is the same model

    # different training data -> the saved file no longer matches -> retrain (and overwrite)
    csv_path = data_dir / "historical_tickets.csv"
    lines = csv_path.read_text(encoding="utf-8").splitlines(keepends=True)
    csv_path.write_text("".join(lines[:-1]), encoding="utf-8")  # drop the last ticket
    _, source = load_or_train(data_dir, index_dir)
    assert source == "trained"
    assert load_or_train(data_dir, index_dir)[1] == "loaded"

    # another scikit-learn version -> retrain (old pickles may not load correctly)
    monkeypatch.setattr(sklearn, "__version__", "0.0.0-test")
    assert load_or_train(data_dir, index_dir)[1] == "trained"


def test_unreadable_saved_classifier_is_retrained(tmp_path):
    data_dir, index_dir = tmp_path / "data", tmp_path / "index"
    data_dir.mkdir()
    index_dir.mkdir()
    shutil.copy(get_settings().data_dir / "historical_tickets.csv", data_dir)
    (index_dir / MODEL_FILE).write_bytes(b"not a joblib file")
    assert load_or_train(data_dir, index_dir)[1] == "trained"


def test_health_does_not_wait_while_warming(monkeypatch):
    def must_not_be_called():
        raise AssertionError("/health waited for the index during warm-up")

    monkeypatch.setattr(main, "warm_up_started", lambda: True)
    monkeypatch.setattr(main, "index_built", lambda: False)
    monkeypatch.setattr(main, "is_ready", lambda: False)
    monkeypatch.setattr(main, "get_index", must_not_be_called)
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["ready"] is False and r.json()["data"]["documents_indexed"] is None


def test_health_reports_ready_after_warm_up():
    with TestClient(app) as client:  # `with` runs the lifespan, which starts the warm-up
        deadline = time.monotonic() + 120
        while True:
            r = client.get("/health")
            assert r.status_code == 200  # 200 while warming too
            if r.json()["data"]["ready"]:
                break
            assert time.monotonic() < deadline, "warm-up did not finish within 120s"
            time.sleep(0.2)
        assert r.json()["data"]["documents_indexed"] > 1000
