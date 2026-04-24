"""End-to-end orchestrator: run any subset of pipeline steps in sequence.

Each step is self-contained and writes its outputs under the derivatives dir.
Steps pass data to each other through a RunContext dataclass. If a step needs
outputs from a prior step that wasn't run, the orchestrator loads them from
disk (preprocessed_raw.fif, per-condition epochs, etc.) or raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mne
import pandas as pd

from ..anatomy import group_by_rois
from ..config import PipelineConfig, dump_config
from ..connectivity import compute_connectivity
from ..events import make_condition_epochs
from ..io import BIDSSubjectData, load_subject, validate_subject_data
from ..logging import get_logger, setup_logger
from ..phase import (
    bandpass_hilbert,
    cfc_tort_mi_all,
    plv_to_reference_with_surrogates,
)
from ..preprocessing import apply_bandpass, apply_notches, apply_reference, detect_bad_channels
from ..spectral import aggregate_bands, compute_psd
from ..tfr import compute_tfr, tfr_log_ratio_baseline
from ..utils import ensure_dir, write_manifest
from ..visualization import (
    plot_bad_channels_qc,
    plot_connectivity_matrix,
    plot_contacts_on_brain,
    plot_psd,
    plot_tfr_roi,
)
from ..visualization.report import ReportBuilder, build_report

log = get_logger("pipeline.run")

AVAILABLE_STEPS = [
    "preprocessing",
    "anatomy",
    "spectral",
    "tfr",
    "phase",
    "cfc",
    "connectivity",
    "stats",
    "report",
]


@dataclass
class RunContext:
    config: PipelineConfig
    out_dir: Path
    report: ReportBuilder
    bids: BIDSSubjectData | None = None
    raw_pre: mne.io.BaseRaw | None = None
    bad_channels: list[str] = field(default_factory=list)
    epochs: dict[str, mne.Epochs] = field(default_factory=dict)
    roi_groups: dict[str, list[str]] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def load_bids(self) -> BIDSSubjectData:
        if self.bids is None:
            self.bids = load_subject(self.config)
            validate_subject_data(self.bids, self.config, strict=False)
        return self.bids

    def get_raw(self) -> mne.io.BaseRaw:
        if self.raw_pre is not None:
            return self.raw_pre
        # Try loading from disk if preprocessing has been run before.
        pre_path = self.out_dir / "preprocessed_raw.fif"
        if pre_path.exists():
            log.info("Loading cached preprocessed raw: %s", pre_path)
            self.raw_pre = mne.io.read_raw_fif(pre_path, preload=True, verbose="WARNING")
            return self.raw_pre
        raise RuntimeError(
            "No preprocessed raw available. Run the 'preprocessing' step first."
        )

    def get_epochs(self, conditions: list[str] | None = None) -> dict[str, mne.Epochs]:
        if self.epochs:
            return self.epochs
        bids = self.load_bids()
        self.epochs = make_condition_epochs(
            self.get_raw(),
            bids.events,
            self.config,
            conditions=conditions,
        )
        return self.epochs


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _step_preprocessing(ctx: RunContext) -> None:
    bids = ctx.load_bids()
    raw = bids.raw.copy()

    # Notch first (line + TI carriers), then broadband bandpass.
    apply_notches(raw, ctx.config)
    apply_bandpass(raw, ctx.config)

    bad_path = ctx.out_dir / "bad_channels.json"
    bad = detect_bad_channels(raw, ctx.config, out_path=bad_path)
    raw.info["bads"] = bad
    ctx.bad_channels = bad

    raw = apply_reference(raw, ctx.config)

    pre_path = ctx.out_dir / "preprocessed_raw.fif"
    raw.save(pre_path, overwrite=True, verbose="WARNING")
    ctx.raw_pre = raw

    # QC figure.
    fig = plot_bad_channels_qc(bad, total_channels=len(bids.raw.ch_names))
    ctx.report.add_figure(fig, title="Bad channels", section="qc")
    log.info("Preprocessing done. n_bad=%d, reference=%s",
             len(bad), ctx.config.preprocessing.reference)


def _step_anatomy(ctx: RunContext) -> None:
    bids = ctx.load_bids()
    raw = ctx.get_raw()
    ctx.roi_groups = group_by_rois(bids.electrodes, raw.ch_names, ctx.config.rois)
    for roi, chans in ctx.roi_groups.items():
        log.info("ROI %s: %d channels", roi, len(chans))

    highlight = [c for chans in ctx.roi_groups.values() for c in chans]
    fig = plot_contacts_on_brain(
        bids.electrodes, highlight=highlight, title="Contacts (ROI channels highlighted)"
    )
    if fig is not None:
        ctx.report.add_figure(fig, title="Anatomy — contacts", section="anatomy")

    # ROI summary as HTML.
    rows = [f"<tr><td>{roi}</td><td>{len(chans)}</td></tr>" for roi, chans in ctx.roi_groups.items()]
    html = "<table><thead><tr><th>ROI</th><th>n_channels</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    ctx.report.add_html(title="ROI channel counts", html=html, section="anatomy")


def _step_spectral(ctx: RunContext) -> None:
    epochs_by_cond = ctx.get_epochs()
    results: dict[str, Any] = {}
    band_frames: list[pd.DataFrame] = []
    sp_dir = ensure_dir(ctx.out_dir / "spectral")
    for cond, epochs in epochs_by_cond.items():
        res = compute_psd(epochs, ctx.config, condition=cond)
        results[cond] = res
        bands_df = aggregate_bands(res, ctx.config.spectral.bands)
        band_frames.append(bands_df)
        fig = plot_psd(res.freqs, res.psd, channel_names=res.ch_names,
                       title=f"PSD — {cond}", fmax=min(200.0, float(res.freqs.max())))
        ctx.report.add_figure(fig, title=f"PSD — {cond}", section="spectral")

    if band_frames:
        all_bands = pd.concat(band_frames, ignore_index=True)
        all_bands.to_csv(sp_dir / "band_power.tsv", sep="\t", index=False)
    ctx.artifacts["spectral"] = results


def _step_tfr(ctx: RunContext) -> None:
    epochs_by_cond = ctx.get_epochs()
    tfr_dir = ensure_dir(ctx.out_dir / "tfr")
    for cond, epochs in epochs_by_cond.items():
        tfr = compute_tfr(epochs, ctx.config, picks="data", return_itc=False)
        tfr_log_ratio_baseline(tfr, ctx.config)
        tfr.save(tfr_dir / f"tfr_{cond}-tfr.h5", overwrite=True, verbose="WARNING")
        # Plot ROI-mean TFR for a small selection.
        if ctx.roi_groups:
            for roi, chans in ctx.roi_groups.items():
                chans_in = [c for c in chans if c in tfr.ch_names]
                if not chans_in:
                    continue
                picks = [tfr.ch_names.index(c) for c in chans_in]
                mean_tfr = tfr.data[picks].mean(axis=0)  # (n_freqs, n_times)
                fig = plot_tfr_roi(
                    mean_tfr, freqs=tfr.freqs, times=tfr.times,
                    title=f"TFR — {cond} — {roi}"
                )
                ctx.report.add_figure(fig, title=f"TFR {cond} / {roi}", section="tfr")


def _step_phase(ctx: RunContext) -> None:
    """PLV-to-TI-envelope for each channel, in active_stim epochs."""
    epochs_by_cond = ctx.get_epochs()
    if "active_stim" not in epochs_by_cond:
        log.warning("No active_stim epochs; skipping phase entrainment step.")
        return
    epochs = epochs_by_cond["active_stim"]
    sfreq = epochs.info["sfreq"]
    f_env = ctx.config.ti.envelope_hz
    bw = ctx.config.phase.envelope.bandwidth_hz
    n_surr = ctx.config.phase.entrainment.n_surrogates

    # Build a reference envelope phase by bandpassing the epoch-mean signal
    # around f_env — in the absence of a stim-monitor channel this works because
    # the TI beat appears in intracranial recordings near the stim site.
    data = epochs.get_data()  # (n_epochs, n_channels, n_times)
    mean_ref = data.mean(axis=(0, 1))  # (n_times,)
    _, ref_phase = bandpass_hilbert(mean_ref, sfreq=sfreq, f_center=f_env, bandwidth=bw)

    # Flatten epochs × time for PLV calculation per channel.
    flat = data.transpose(1, 0, 2).reshape(data.shape[1], -1)
    # Repeat the reference phase across epochs so shapes match.
    n_epochs = data.shape[0]
    ref_phase_rep = np.tile(ref_phase, n_epochs)

    result = plv_to_reference_with_surrogates(
        data=flat,
        ch_names=epochs.ch_names,
        reference_phase=ref_phase_rep,
        sfreq=sfreq,
        f_center=f_env,
        bandwidth=bw,
        n_surrogates=n_surr,
    )
    phase_dir = ensure_dir(ctx.out_dir / "phase")
    pd.DataFrame(
        {"channel": result.ch_names, "plv": result.plv, "p_value": result.p_values}
    ).to_csv(phase_dir / "plv_to_envelope.tsv", sep="\t", index=False)


def _step_cfc(ctx: RunContext) -> None:
    if not ctx.config.phase.cfc.enabled:
        return
    epochs_by_cond = ctx.get_epochs()
    cfc_cfg = ctx.config.phase.cfc
    phase_band = tuple(cfc_cfg.phase_band)
    amp_bands = [tuple(b) for b in cfc_cfg.amp_bands]
    cfc_dir = ensure_dir(ctx.out_dir / "phase")
    for cond, epochs in epochs_by_cond.items():
        # Concatenate all epochs for CFC MI estimation (Tort MI needs long segments).
        data = epochs.get_data().mean(axis=0)  # shape (n_channels, n_times) avg across trials
        res = cfc_tort_mi_all(
            data=data,
            ch_names=epochs.ch_names,
            sfreq=epochs.info["sfreq"],
            phase_band=phase_band,
            amp_bands=amp_bands,
            n_bins=cfc_cfg.n_bins,
        )
        # Save MI matrix (ch × amp_bands).
        df = pd.DataFrame(
            res.mi,
            index=pd.Index(res.ch_names, name="channel"),
            columns=[f"{lo}-{hi}Hz" for lo, hi in amp_bands],
        )
        df.to_csv(cfc_dir / f"cfc_mi_{cond}.tsv", sep="\t")


def _step_connectivity(ctx: RunContext) -> None:
    epochs_by_cond = ctx.get_epochs()
    con_dir = ensure_dir(ctx.out_dir / "connectivity")
    for cond, epochs in epochs_by_cond.items():
        results = compute_connectivity(epochs, ctx.config)
        for r in results:
            stem = f"con_{r.method}_{r.band}_{cond}"
            np_path = con_dir / f"{stem}.npz"
            import numpy as np

            np.savez(np_path, matrix=r.matrix, ch_names=np.array(r.ch_names))
            fig = plot_connectivity_matrix(
                r.matrix, labels=r.ch_names, title=f"{r.method} — {r.band} — {cond}"
            )
            ctx.report.add_figure(fig, title=stem, section="connectivity")


def _step_stats(ctx: RunContext) -> None:
    # Lightweight default: contrast active_stim vs no_stim TFR on first data channel.
    epochs_by_cond = ctx.get_epochs()
    if {"active_stim", "no_stim"}.issubset(epochs_by_cond.keys()):
        from ..stats import paired_condition_tfr_contrast

        res = paired_condition_tfr_contrast(
            epochs_by_cond["active_stim"], epochs_by_cond["no_stim"], ctx.config, pick=0
        )
        log.info(
            "Stats: %d clusters, min_p=%.3f",
            len(res.clusters),
            float(res.cluster_p_values.min()) if len(res.cluster_p_values) else 1.0,
        )


def _step_report(ctx: RunContext) -> None:
    ctx.report.save()


STEP_REGISTRY = {
    "preprocessing": _step_preprocessing,
    "anatomy": _step_anatomy,
    "spectral": _step_spectral,
    "tfr": _step_tfr,
    "phase": _step_phase,
    "cfc": _step_cfc,
    "connectivity": _step_connectivity,
    "stats": _step_stats,
    "report": _step_report,
}


# numpy import deferred to avoid unused-if-disabled warnings.
import numpy as np  # noqa: E402


def run_pipeline(config: PipelineConfig, steps: list[str]) -> Path:
    """Run the requested steps in order. Returns the derivatives output directory."""
    out_dir = ensure_dir(config.derivatives_dir())
    setup_logger(log_file=out_dir / "pipeline.log")
    dump_config(config, out_dir / "config_snapshot.yaml")

    # Always include the report step at the end if the user didn't disable it.
    if "report" not in steps and config.report.enabled:
        steps = [*steps, "report"]

    report = build_report(config, out_dir)
    ctx = RunContext(config=config, out_dir=out_dir, report=report)

    for step in steps:
        if step not in STEP_REGISTRY:
            raise ValueError(
                f"Unknown step {step!r}. Available: {sorted(STEP_REGISTRY)}"
            )
        log.info("==== step: %s ====", step)
        STEP_REGISTRY[step](ctx)
        write_manifest(out_dir, config, step=step)

    return out_dir
