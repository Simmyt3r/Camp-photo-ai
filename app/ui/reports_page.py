"""Processing reports browser and export screen."""
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
from app.ui.activity import notify_activity
from app.ui.widgets import Card, PageHeader


class ReportsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._current_run_id: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 26, 28, 26)
        outer.setSpacing(16)

        header = PageHeader(
            "Reports",
            "Inspect previous processing runs and export a portable summary.",
        )
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        header.trailing.addWidget(refresh_btn)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        list_card = Card("Processing runs")
        self.run_count_label = QLabel("")
        self.run_count_label.setObjectName("cardHint")
        list_card.body.addWidget(self.run_count_label)

        self.run_list = QListWidget()
        self.run_list.currentItemChanged.connect(self._on_selection_changed)
        list_card.body.addWidget(self.run_list, stretch=1)
        body.addWidget(list_card, stretch=1)

        detail_card = Card(
            "Run details",
            "Select a run to see its performance, thresholds, and outcome.",
        )

        self.detail_view = QTextEdit()
        self.detail_view.setObjectName("logView")
        self.detail_view.setReadOnly(True)
        detail_card.body.addWidget(self.detail_view, stretch=1)

        export_row = QHBoxLayout()
        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.setObjectName("primaryButton")
        self.export_json_btn.clicked.connect(lambda: self._export("json"))
        export_row.addWidget(self.export_json_btn)

        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.setObjectName("secondaryButton")
        self.export_csv_btn.clicked.connect(lambda: self._export("csv"))
        export_row.addWidget(self.export_csv_btn)
        export_row.addStretch(1)
        detail_card.body.addLayout(export_row)

        body.addWidget(detail_card, stretch=2)
        outer.addLayout(body, stretch=1)

        self._set_export_enabled(False)
        self.refresh()

    def _set_export_enabled(self, enabled: bool) -> None:
        self.export_json_btn.setEnabled(enabled)
        self.export_csv_btn.setEnabled(enabled)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.run_list.clear()
        self._current_run_id = None
        self._set_export_enabled(False)

        try:
            with get_session() as session:
                runs = (
                    session.query(ProcessingRun)
                    .order_by(ProcessingRun.id.desc())
                    .all()
                )
                for run in runs:
                    status = "Complete" if run.finished_at else "Interrupted"
                    label = (
                        f"Run #{run.id} • {status}\n"
                        f"{run.started_at.strftime('%Y-%m-%d %H:%M')} • "
                        f"{run.total_photos} photos • {run.auto_matched} matched"
                    )
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, run.id)
                    self.run_list.addItem(item)
        except Exception as exc:
            self.run_count_label.setText(f"Could not load processing runs: {exc}")
            self.detail_view.setPlainText("Processing-run history could not be loaded.")
            return

        self.run_count_label.setText(
            f"{len(runs)} run{'s' if len(runs) != 1 else ''} recorded"
        )

        if runs:
            self.run_list.setCurrentRow(0)
        else:
            self.detail_view.setPlainText(
                "No processing runs yet. Process a folder of photos first, "
                "then its report will appear here."
            )

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return

        run_id = current.data(Qt.UserRole)
        self._current_run_id = run_id

        with get_session() as session:
            run = session.get(ProcessingRun, run_id)
            if run is None:
                self._set_export_enabled(False)
                return
            report = build_report(run)

        status = "Complete" if report.finished_at else "Interrupted / unfinished"
        lines = [
            f"RUN #{run_id}  •  {status}",
            "",
            "TIMING",
            f"Started:          {report.started_at}",
            f"Finished:         {report.finished_at or 'Not finished'}",
            f"Total time:       {report.total_processing_seconds:.1f} sec",
            f"Average speed:    {report.average_speed_images_per_sec:.2f} images/sec",
            "",
            "FOLDERS",
            f"Input:            {report.input_dir}",
            f"Output:           {report.output_dir}",
            "",
            "RESULTS",
            f"Photos processed: {report.total_photos:,}",
            f"Faces detected:   {report.total_faces:,}",
            f"Auto-matched:     {report.auto_matched:,}",
            f"Needs review:     {report.review_count:,}",
            f"Unmatched:        {report.unmatched_count:,}",
            f"Errors:           {report.error_count:,}",
            "",
            "MATCHING CONFIGURATION",
            f"Model version:        {report.model_version}",
            f"Auto-match threshold: {report.auto_match_threshold}",
            f"Review threshold:     {report.review_threshold}",
        ]
        self.detail_view.setPlainText("\n".join(lines))
        self._set_export_enabled(True)

    def _export(self, fmt: str) -> None:
        if self._current_run_id is None:
            return

        with get_session() as session:
            run = session.get(ProcessingRun, self._current_run_id)
            if run is None:
                return
            report = build_report(run)

        default_name = f"camp-photo-run-{self._current_run_id}.{fmt}"
        filter_str = "JSON files (*.json)" if fmt == "json" else "CSV files (*.csv)"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            f"Export report as {fmt.upper()}",
            default_name,
            filter_str,
        )
        if not path_str:
            return

        dest = Path(path_str)
        report.to_json(dest) if fmt == "json" else report.to_csv(dest)
        QMessageBox.information(
            self,
            "Report exported",
            f"The report was written to:\n{dest}",
        )
        notify_activity(f"Report exported as {fmt.upper()}: {dest.name}", "success")
