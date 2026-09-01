"""Reports screen (section 20): browse past ProcessingRun rows and
export any of them via the same build_report()/ProcessingReport used by
`python -m app.cli report` -- one source of truth for report content,
just two ways to reach it."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.database.db import get_session
from app.database.models import ProcessingRun
from app.services.reporting import build_report


class ReportsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._current_run_id: int | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        left = QVBoxLayout()
        header = QLabel("Reports")
        header.setObjectName("pageTitle")
        left.addWidget(header)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        left.addWidget(refresh_btn)

        self.run_list = QListWidget()
        self.run_list.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.run_list, stretch=1)
        layout.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Details"))
        self.detail_view = QTextEdit()
        self.detail_view.setObjectName("logView")
        self.detail_view.setReadOnly(True)
        right.addWidget(self.detail_view, stretch=1)

        export_row = QHBoxLayout()
        export_json_btn = QPushButton("Export as JSON")
        export_json_btn.setObjectName("primaryButton")
        export_json_btn.clicked.connect(lambda: self._export("json"))
        export_row.addWidget(export_json_btn)

        export_csv_btn = QPushButton("Export as CSV")
        export_csv_btn.clicked.connect(lambda: self._export("csv"))
        export_row.addWidget(export_csv_btn)
        export_row.addStretch(1)
        right.addLayout(export_row)

        layout.addLayout(right, stretch=2)
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.run_list.clear()
        with get_session() as session:
            runs = session.query(ProcessingRun).order_by(ProcessingRun.id.desc()).all()
            for run in runs:
                status = "complete" if run.finished_at else "incomplete/interrupted"
                label = (
                    f"Run #{run.id} -- {run.started_at.strftime('%Y-%m-%d %H:%M')} "
                    f"({status}) -- {run.total_photos} photos, {run.auto_matched} auto-matched"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, run.id)
                self.run_list.addItem(item)

        if runs:
            self.run_list.setCurrentRow(0)
        else:
            self.detail_view.setPlainText("No processing runs yet -- run a batch from Process Photos first.")
            self._current_run_id = None

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        run_id = current.data(Qt.UserRole)
        self._current_run_id = run_id
        with get_session() as session:
            run = session.get(ProcessingRun, run_id)
            if run is None:
                return
            report = build_report(run)

        lines = [
            f"Run #{run_id}",
            "",
            f"Started:  {report.started_at}",
            f"Finished: {report.finished_at or '(not finished -- interrupted or still running)'}",
            f"Input:    {report.input_dir}",
            f"Output:   {report.output_dir}",
            "",
            f"Photos processed:   {report.total_photos:,}",
            f"Faces detected:     {report.total_faces:,}",
            f"Auto-matched:       {report.auto_matched:,}",
            f"Sent to review:     {report.review_count:,}",
            f"Unmatched:          {report.unmatched_count:,}",
            f"Errors:             {report.error_count:,}",
            "",
            f"Total time:         {report.total_processing_seconds:.1f}s",
            f"Average speed:      {report.average_speed_images_per_sec:.2f} images/sec",
            "",
            f"Model version:          {report.model_version}",
            f"Auto-match threshold:   {report.auto_match_threshold}",
            f"Review threshold:       {report.review_threshold}",
        ]
        self.detail_view.setPlainText("\n".join(lines))

    def _export(self, fmt: str) -> None:
        if self._current_run_id is None:
            QMessageBox.warning(self, "No run selected", "Select a run from the list first.")
            return

        with get_session() as session:
            run = session.get(ProcessingRun, self._current_run_id)
            if run is None:
                return
            report = build_report(run)

        default_name = f"report_run{self._current_run_id}.{fmt}"
        filter_str = "JSON files (*.json)" if fmt == "json" else "CSV files (*.csv)"
        path_str, _ = QFileDialog.getSaveFileName(self, f"Export report as {fmt.upper()}", default_name, filter_str)
        if not path_str:
            return

        dest = Path(path_str)
        report.to_json(dest) if fmt == "json" else report.to_csv(dest)
        QMessageBox.information(self, "Exported", f"Report written to {dest}")
