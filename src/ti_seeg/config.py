"""Pydantic config schema + YAML loader with defaults-merge."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class BadChannelStrategy(BaseModel):
    method: str = "variance_kurtosis"
    variance_z_thresh: float = 5.0
    kurtosis_z_thresh: float = 5.0
    flat_thresh_uv: float = 0.5


class PreprocessingConfig(BaseModel):
    line_freq: float = 60.0
    line_harmonics: int = 6
    notch_carriers: bool = True
    carrier_harmonics: int = 4
    notch_width_hz: float = 2.0
    bandpass: list[float | None] = Field(default_factory=lambda: [0.5, None])
    reference: str = "bipolar"
    crop: list[float | None] = Field(default_factory=lambda: [None, None])
    target_sfreq: float | None = None
    bad_channel_strategy: BadChannelStrategy = Field(default_factory=BadChannelStrategy)

    @field_validator("reference")
    @classmethod
    def _check_reference(cls, v: str) -> str:
        if v not in {"bipolar", "car", "monopolar"}:
            raise ValueError(f"reference must be bipolar|car|monopolar, got {v!r}")
        return v


class SlidingConfig(BaseModel):
    window_sec: float = 2.0
    overlap: float = 0.5


class EventsConfig(BaseModel):
    label_map: dict[str, str] = Field(default_factory=dict)
    epoch_window: dict[str, list[float]] = Field(default_factory=dict)
    sliding: SlidingConfig = Field(default_factory=SlidingConfig)


class SpectralConfig(BaseModel):
    enabled: bool = True
    method: str = "multitaper"
    fmin: float = 1.0
    fmax: float = 200.0
    bandwidth_hz: float = 2.0
    bands: dict[str, list[float]] = Field(default_factory=dict)
    contrasts: list[list[str]] = Field(default_factory=list)


class TFRBaseline(BaseModel):
    tmin: float = -1.0
    tmax: float = -0.1
    mode: str = "logratio"


class TFRConfig(BaseModel):
    enabled: bool = True
    method: str = "morlet"
    fmin: float = 2.0
    fmax: float = 200.0
    n_freqs: int = 40
    freq_scale: str = "log"
    n_cycles_rule: str = "freqs / 2"
    baseline: TFRBaseline = Field(default_factory=TFRBaseline)


class EnvelopeConfig(BaseModel):
    bandwidth_hz: float = 2.0


class EntrainmentConfig(BaseModel):
    n_surrogates: int = 200
    surrogate_method: str = "time_shift"


class CFCConfig(BaseModel):
    enabled: bool = True
    phase_band: list[float] = Field(default_factory=lambda: [4.0, 8.0])
    amp_bands: list[list[float]] = Field(default_factory=lambda: [[30.0, 80.0], [80.0, 150.0]])
    method: str = "tort"
    n_bins: int = 18


class PhaseConfig(BaseModel):
    enabled: bool = True
    envelope: EnvelopeConfig = Field(default_factory=EnvelopeConfig)
    entrainment: EntrainmentConfig = Field(default_factory=EntrainmentConfig)
    cfc: CFCConfig = Field(default_factory=CFCConfig)


class ConnectivityConfig(BaseModel):
    enabled: bool = True
    method: list[str] = Field(default_factory=lambda: ["coh", "wpli", "plv"])
    bands: dict[str, list[float]] = Field(default_factory=dict)
    within_roi: bool = True
    between_roi: bool = True


class StatsConfig(BaseModel):
    enabled: bool = True
    cluster_alpha: float = 0.05
    n_permutations: int = 1000
    tail: int = 0


class ReportConfig(BaseModel):
    enabled: bool = True
    include_sections: list[str] = Field(
        default_factory=lambda: [
            "qc",
            "anatomy",
            "spectral",
            "tfr",
            "phase",
            "connectivity",
            "stats",
        ]
    )


class TIStimConfig(BaseModel):
    block_label: str = "inhibition"
    f1_hz: float
    f2_hz: float
    envelope_hz: float

    @property
    def carriers(self) -> list[float]:
        return [self.f1_hz, self.f2_hz]


class AnatomyConfig(BaseModel):
    t1_path: str | None = None
    freesurfer_subjects_dir: str | None = None
    freesurfer_subject_id: str | None = None


class PipelineConfig(BaseModel):
    # Identifiers
    subject: str
    session: str | None = None
    task: str
    run: str | None = None
    acquisition: str | None = None

    # Paths
    bids_root: str
    derivatives_root: str

    # Anatomy (optional)
    anatomy: AnatomyConfig = Field(default_factory=AnatomyConfig)

    # TI parameters
    ti: TIStimConfig

    # ROIs: canonical_name -> list of match substrings
    rois: dict[str, list[str]] = Field(default_factory=dict)

    # Analysis modules
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)
    spectral: SpectralConfig = Field(default_factory=SpectralConfig)
    tfr: TFRConfig = Field(default_factory=TFRConfig)
    phase: PhaseConfig = Field(default_factory=PhaseConfig)
    connectivity: ConnectivityConfig = Field(default_factory=ConnectivityConfig)
    stats: StatsConfig = Field(default_factory=StatsConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    def derivatives_dir(self) -> Path:
        parts = [
            self.derivatives_root,
            f"sub-{self.subject}",
        ]
        if self.session:
            parts.append(f"ses-{self.session}")
        run_part = f"task-{self.task}"
        if self.run:
            run_part += f"_run-{self.run}"
        parts.append(run_part)
        return Path(*parts)


# ---------------------------------------------------------------------------
# Loading / merging
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursive dict merge — `override` wins for leaves, dicts are merged."""
    out = deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping at top level of {path}")
    return data


def load_config(subject_config_path: str | Path) -> PipelineConfig:
    """Load a subject config and merge with its `defaults_file` (if specified)."""
    subject_path = Path(subject_config_path).resolve()
    raw = load_yaml(subject_path)

    defaults_file = raw.pop("defaults_file", None)
    merged: dict[str, Any]
    if defaults_file is not None:
        defaults_path = (subject_path.parent / defaults_file).resolve()
        if not defaults_path.exists():
            # Allow absolute or relative-to-cwd paths.
            alt = Path(defaults_file).resolve()
            defaults_path = alt if alt.exists() else defaults_path
        defaults = load_yaml(defaults_path)
        merged = _deep_merge(defaults, raw)
    else:
        merged = raw

    return PipelineConfig.model_validate(merged)


def dump_config(config: PipelineConfig, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(config.model_dump(), f, sort_keys=False)
