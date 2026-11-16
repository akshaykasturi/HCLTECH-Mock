"""Tests for the template-grouped split (app/uc4/ml/features.py): no template in both train and test, file reused."""
import json

import pytest

from app.uc4.ml import features as f


def test_template_id_masks_varying_values() -> None:
    a = f.template_id(f.clean_text("Upstream inventory-db did not respond within 10000 ms"))
    b = f.template_id(f.clean_text("Upstream payments-svc did not respond within 3000 ms"))
    assert a == b == "upstream <SVC> did not respond within <V> ms"
    c = f.template_id(f.clean_text("Field 'amount' is required (received customer_email=jane@example.com)"))
    assert c == f.template_id(f.clean_text("Field 'currency' is required")) == "field <Q> is required"


def test_no_template_in_both_train_and_test(tmp_path) -> None:
    X_train, X_test, y_train, y_test = f.get_group_split(tmp_path / "split.json")
    train_t = set(f.get_group_templates(X_train.index))
    test_t = set(f.get_group_templates(X_test.index))
    assert train_t and test_t and not train_t & test_t
    assert set(y_test) == set(y_train)  # every class is tested and trained
    assert len(X_train) + len(X_test) == 863


def test_one_template_per_class_held_out(tmp_path) -> None:
    f.get_group_split(tmp_path / "split.json")
    saved = json.loads((tmp_path / "split.json").read_text(encoding="utf-8"))
    X, y, meta = f.load_pool()
    owner = f._template_owner(meta, y)
    held_classes = [owner[t] for t in saved["test_templates"]]
    assert sorted(held_classes) == sorted(set(y))


def test_split_file_is_reused_across_runs(tmp_path) -> None:
    path = tmp_path / "split.json"
    first = f.get_group_split(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    # Hold out a different set on purpose: the function must follow the file, not recompute.
    X, y, meta = f.load_pool()
    other = f.template_rotations(meta, y)[1]
    saved["test_templates"] = other
    saved["test_idx"] = [int(i) for i in meta.index[meta["template_id"].isin(other)]]
    path.write_text(json.dumps(saved), encoding="utf-8")
    second = f.get_group_split(path)
    assert sorted(second[1].index) == saved["test_idx"]
    assert sorted(second[1].index) != sorted(first[1].index)
    third = f.get_group_split(path)
    assert list(third[1].index) == list(second[1].index)


def test_split_file_from_other_data_is_refused(tmp_path) -> None:
    path = tmp_path / "split.json"
    f.get_group_split(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["fingerprint"] = "different-data"
    path.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(RuntimeError):
        f.get_group_split(path)


def test_rotation_holds_out_every_template_at_least_once() -> None:
    X, y, meta = f.load_pool()
    rounds = f.template_rotations(meta, y)
    owner = f._template_owner(meta, y)
    held = set().union(*map(set, rounds))
    for cls in set(owner.values()):
        owned = {t for t, c in owner.items() if c == cls}
        assert len(owned & held) >= min(len(owned), f.N_ROTATIONS)
    for r in rounds:
        assert len(r) == len(set(owner.values()))  # one template per class per round
