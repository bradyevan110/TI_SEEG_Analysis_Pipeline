"""HTML report assembly via mne.Report."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import mne

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("visualization.report")


def save_figure(fig: plt.Figure, path: Path, dpi: int = 120) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


class ReportBuilder:
    """Accumulate figures and write a single HTML report at the end."""

    def __init__(self, config: PipelineConfig, out_dir: Path):
        self.config = config
        self.out_dir = out_dir
        title = f"TI_SEEG sub-{config.subject} task-{config.task}"
        if config.run:
            title += f" run-{config.run}"
        self.report = mne.Report(title=title, verbose="WARNING")
        self.figures_dir = out_dir / "figures"
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self._n_added = 0

    def add_figure(
        self,
        fig: plt.Figure,
        title: str,
        section: str = "other",
        caption: str | None = None,
    ) -> Path:
        slug = title.lower().replace(" ", "_").replace("/", "_")
        fig_path = self.figures_dir / f"{section}_{slug}.png"
        save_figure(fig, fig_path)
        self.report.add_image(image=fig_path, title=title, section=section, caption=caption)
        self._n_added += 1
        return fig_path

    def add_html(self, title: str, html: str, section: str = "other") -> None:
        self.report.add_html(html=html, title=title, section=section)
        self._n_added += 1

    def add_code(self, title: str, code: str, language: str = "yaml", section: str = "other") -> None:
        html = f"<pre><code class='language-{language}'>{code}</code></pre>"
        self.report.add_html(html=html, title=title, section=section)
        self._n_added += 1

    def save(self, overwrite: bool = True) -> Path:
        out_path = self.out_dir / "report.html"
        if self._n_added == 0:
            log.warning("Report is empty — nothing to save (skipping %s).", out_path)
            return out_path
        self.report.save(out_path, overwrite=overwrite, open_browser=False)
        log.info("Report saved: %s", out_path)
        return out_path


def build_report(config: PipelineConfig, out_dir: Path) -> ReportBuilder:
    return ReportBuilder(config=config, out_dir=out_dir)
