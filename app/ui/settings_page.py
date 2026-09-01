"""Settings screen (section 33): edits app/config/settings.py's Settings
dataclass and saves it to data/settings.json via Settings.save(). No
new persistence logic here -- this is a form on top of what Phase 1
already built."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.config.settings import Settings


class SettingsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.setSpacing(16)

        header = QLabel("Settings")
        header.setObjectName("pageTitle")
        outer.addWidget(header)

        warning = QLabel(
            "Changes to Database path or Models folder take effect on next restart, "
            "not immediately -- this session already has both open."
        )
        warning.setObjectName("hintLabel")
        warning.setWordWrap(True)
        outer.addWidget(warning)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_dir_edit = self._path_row(form, "Input folder")
        self.output_dir_edit = self._path_row(form, "Output folder")
        self.models_dir_edit = self._path_row(form, "Models folder")
        self.logs_dir_edit = self._path_row(form, "Logs folder")

        self.database_path_label = QLineEdit()
        self.database_path_label.setEnabled(False)
        form.addRow("Database path (read-only)", self.database_path_label)

        form.addRow(self._divider())

        self.auto_threshold_spin = self._threshold_spin()
        form.addRow("Auto-match threshold", self.auto_threshold_spin)
        self.review_threshold_spin = self._threshold_spin()
        form.addRow("Review threshold", self.review_threshold_spin)
        self.margin_spin = self._threshold_spin()
        form.addRow("Minimum score margin", self.margin_spin)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["top_k", "max", "mean", "centroid"])
        form.addRow("Match strategy", self.strategy_combo)

        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 10)
        form.addRow("Top-K (for top_k strategy)", self.top_k_spin)

        form.addRow(self._divider())

        self.processing_mode_combo = QComboBox()
        self.processing_mode_combo.addItems(["auto", "cpu", "gpu"])
        form.addRow("Processing mode", self.processing_mode_combo)

        self.worker_count_spin = QSpinBox()
        self.worker_count_spin.setRange(1, 32)
        self.worker_count_spin.setToolTip(
            "Not yet used by the pipeline -- multiprocessing is planned but not implemented "
            "(see docs/PERFORMANCE.md). Saved for when it is."
        )
        form.addRow("Worker count (not yet used)", self.worker_count_spin)

        form.addRow(self._divider())

        self.duplicate_policy_combo = QComboBox()
        self.duplicate_policy_combo.addItems(["skip", "keep", "rename"])
        form.addRow("Duplicate policy", self.duplicate_policy_combo)

        self.phash_spin = QSpinBox()
        self.phash_spin.setRange(0, 64)
        form.addRow("Perceptual hash threshold", self.phash_spin)

        self.max_dimension_spin = QSpinBox()
        self.max_dimension_spin.setRange(512, 16384)
        self.max_dimension_spin.setSingleStep(256)
        form.addRow("Max image dimension (px)", self.max_dimension_spin)

        self.cache_checkbox = QCheckBox("Skip unchanged photos on re-run")
        form.addRow("Caching", self.cache_checkbox)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        form.addRow("Log level", self.log_level_combo)

        outer.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        outer.addWidget(self.status_label)

        button_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        button_row.addWidget(save_btn)

        reset_btn = QPushButton("Restore Defaults")
        reset_btn.clicked.connect(self._restore_defaults)
        button_row.addWidget(reset_btn)
        button_row.addStretch(1)
        outer.addLayout(button_row)

        outer.addStretch(1)
        self._load_into_form(context.settings)

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _threshold_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.01)
        spin.setDecimals(3)
        return spin

    def _path_row(self, form: QFormLayout, label: str) -> QLineEdit:
        row = QHBoxLayout()
        edit = QLineEdit()
        row.addWidget(edit, stretch=1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse(edit))
        row.addWidget(browse)
        container = QWidget()
        container.setLayout(row)
        form.addRow(label, container)
        return edit

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder", edit.text() or "")
        if path:
            edit.setText(path)

    def _load_into_form(self, settings: Settings) -> None:
        self.input_dir_edit.setText(settings.input_dir)
        self.output_dir_edit.setText(settings.output_dir)
        self.models_dir_edit.setText(settings.models_dir)
        self.logs_dir_edit.setText(settings.logs_dir)
        self.database_path_label.setText(settings.database_path)

        self.auto_threshold_spin.setValue(settings.auto_match_threshold)
        self.review_threshold_spin.setValue(settings.review_threshold)
        self.margin_spin.setValue(settings.minimum_score_margin)
        self.strategy_combo.setCurrentText(settings.match_strategy)
        self.top_k_spin.setValue(settings.top_k)

        self.processing_mode_combo.setCurrentText(settings.processing_mode)
        self.worker_count_spin.setValue(settings.worker_count)

        self.duplicate_policy_combo.setCurrentText(settings.duplicate_policy)
        self.phash_spin.setValue(settings.perceptual_hash_threshold)
        self.max_dimension_spin.setValue(settings.max_image_dimension)
        self.cache_checkbox.setChecked(settings.cache_enabled)
        self.log_level_combo.setCurrentText(settings.log_level)

        self.status_label.setText("")

    def _save(self) -> None:
        if self.review_threshold_spin.value() >= self.auto_threshold_spin.value():
            QMessageBox.warning(
                self, "Check your thresholds",
                "Review threshold is usually set below the auto-match threshold, "
                "so there's a middle band that goes to human review instead of jumping "
                "straight from 'auto-match' to 'unmatched'. Saving anyway is allowed, "
                "but double-check this is what you want.",
            )

        updated = replace(
            self.context.settings,
            input_dir=self.input_dir_edit.text().strip(),
            output_dir=self.output_dir_edit.text().strip(),
            models_dir=self.models_dir_edit.text().strip(),
            logs_dir=self.logs_dir_edit.text().strip(),
            auto_match_threshold=self.auto_threshold_spin.value(),
            review_threshold=self.review_threshold_spin.value(),
            minimum_score_margin=self.margin_spin.value(),
            match_strategy=self.strategy_combo.currentText(),
            top_k=self.top_k_spin.value(),
            processing_mode=self.processing_mode_combo.currentText(),
            worker_count=self.worker_count_spin.value(),
            duplicate_policy=self.duplicate_policy_combo.currentText(),
            perceptual_hash_threshold=self.phash_spin.value(),
            max_image_dimension=self.max_dimension_spin.value(),
            cache_enabled=self.cache_checkbox.isChecked(),
            log_level=self.log_level_combo.currentText(),
        )
        updated.save()
        self.context.settings = updated
        self.status_label.setText(
            "Saved to data/settings.json. Threshold/duplicate/cache/logging changes apply to the "
            "next process/evaluate/benchmark run in this session; path changes need a restart."
        )

    def _restore_defaults(self) -> None:
        confirm = QMessageBox.question(
            self, "Restore defaults?",
            "This resets every field below to its built-in default (not yet saved -- "
            "click Save Settings afterward to make it permanent). Continue?",
        )
        if confirm == QMessageBox.Yes:
            self._load_into_form(Settings())

    def on_shown(self) -> None:
        self._load_into_form(self.context.settings)
