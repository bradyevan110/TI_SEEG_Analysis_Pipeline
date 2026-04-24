"""Shared utilities: manifest writing, hashing, ROI matching."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import PipelineConfig


def config_hash(config: PipelineConfig) -> str:
    payload = json.dumps(config.model_dump(), sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def write_manifest(
    out_dir: Path,
    config: PipelineConfig,
    step: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append a manifest entry documenting when/how a step was run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "run_manifest.json"

    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {"runs": []}

    entry = {
        "step": step,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "config_hash": config_hash(config),
        "subject": config.subject,
        "session": config.session,
        "task": config.task,
        "run": config.run,
    }
    if extra:
        entry.update(extra)
    manifest["runs"].append(entry)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path


def match_roi(label: str | None, patterns: list[str]) -> bool:
    """Case-insensitive substring match between an anatomical label and ROI patterns."""
    if not label:
        return False
    label_lower = label.lower()
    return any(p.lower() in label_lower for p in patterns)


def group_channels_by_roi(
    channel_labels: dict[str, str | None],
    rois: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Return {roi_name: [channel_names]} given {channel_name: anat_label}."""
    out: dict[str, list[str]] = {name: [] for name in rois}
    for ch, label in channel_labels.items():
        for roi_name, patterns in rois.items():
            if match_roi(label, patterns):
                out[roi_name].append(ch)
    return out


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
