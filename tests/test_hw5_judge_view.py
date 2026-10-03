"""The judge view serves development predictions only."""

import json

from analysis.review_app import hw5


def _state(tmp_path, preds):
    (tmp_path / "judges").mkdir()
    (tmp_path / "hw5_labels").mkdir()
    ids = {"d1": "dev", "t1": "test"}
    labels = [
        {"trace_id": t, "session_id": f"s-{t}", "scenario_id": "support-0001", "mode": hw5.MODE, "label": 1}
        for t in ids
    ]
    (tmp_path / "hw5_labels" / f"{hw5.MODE}.jsonl").write_text("\n".join(json.dumps(r) for r in labels))
    (tmp_path / "splits.json").write_text(json.dumps({hw5.MODE: {"dev": ["d1"], "test": ["t1"], "train": []}}))
    (tmp_path / "judges" / f"_history_{hw5.MODE}.json").write_text(json.dumps({"versions": [{"judge_id": "j-v0"}]}))
    (tmp_path / "judges" / "j-v0.json").write_text(json.dumps({
        "prompt_hash": "h", "version": 0,
        "predictions": {"h": preds}, "critiques": {"h": {t: f"critique {t}" for t in preds}},
    }))


def test_test_predictions_are_never_served(tmp_path):
    _state(tmp_path, {"d1": 0, "t1": 0})
    view = hw5.judge_view(tmp_path)
    assert set(view["items"]) == {"s-d1"}


def test_verdict_and_agreement_follow_the_human_label(tmp_path):
    _state(tmp_path, {"d1": 0})
    item = hw5.judge_view(tmp_path)["items"]["s-d1"]
    assert item == {"verdict": "Fail", "critique": "critique d1", "human": "Pass", "agree": False}


def test_no_judge_yet_gives_an_empty_view(tmp_path):
    assert hw5.judge_view(tmp_path) == {"judge_id": None, "items": {}}
