from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_prediction(mode: str, tmp_path: Path) -> Path:
    output_dir = tmp_path / mode
    output_path = output_dir / f"{mode}.json"
    csv_path = output_dir / f"{mode}.csv"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_prediction.py",
            "--mode",
            mode,
            "--output-dir",
            str(output_dir),
            "--output",
            str(output_path),
            "--csv-output",
            str(csv_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return output_path


def test_next_section_writes_latest_predictions(tmp_path: Path) -> None:
    path = run_prediction("next_section", tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["matches"]
    assert data.get("warnings") == []
    assert data.get("skipped_matches") == []


def test_all_unplayed_writes_separate_predictions(tmp_path: Path) -> None:
    path = run_prediction("all_unplayed", tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["matches"]
    assert data.get("warnings") == []
    assert data.get("skipped_matches") == []


def test_shadow_model_writes_to_separate_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "primary"
    output_path = output_dir / "latest.json"
    shadow_path = tmp_path / "shadow" / "latest.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_prediction.py",
            "--mode",
            "next_section",
            "--output-dir",
            str(output_dir),
            "--output",
            str(output_path),
            "--shadow-model-dir",
            "Models/weather_removed_v1",
            "--shadow-output",
            str(shadow_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert output_path.exists()
    assert shadow_path.exists()
    primary = json.loads(output_path.read_text(encoding="utf-8"))
    shadow = json.loads(shadow_path.read_text(encoding="utf-8"))
    assert len(primary["matches"]) == len(shadow["matches"])
