"""Grouped settings UI for storage, matching, processing, and app behavior."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.config.settings import Settings
from app.ui.widgets import Card, PageHeader


class SettingsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 26, 28, 26)
        outer.setSpacing(14)

        outer.addWidget(PageHeader(
            "Settings",
            "Tune storage, matching thresholds, processing mode, duplicate handling, and logging.",
        ))

        warning = QLabel(
            "Database and model-folder changes require an app restart because those resources "
            "are already open in this session."
        )
        warning.setObjectName("warningBanner")
        warning.setWordWrap(True)
        outer.addWidget(warning)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)

        storage_card = Card(
            "Storage & folders",
            "Where CampPhoto AI reads, writes, stores models, and writes logs.",
        )
        storage_form = QFormLayout()
        storage_form.setSpacing(10)
        self.input_dir_edit = self._path_row(storage_form, "Default input")
        self.output_dir_edit = self._path_row(storage_form, "Output folder")
        self.models_dir_edit = self._path_row(storage_form, "Models folder")
        self.logs_dir_edit = self._path_row(storage_form, "Logs folder")

        self.database_path_label = QLineEdit()
        self.database_path_label.setReadOnly(True)
        self.database_path_label.setToolTip("Database location cannot be changed from this screen.")
        storage_form.addRow("Database", self.database_path_label)
        storage_card.body.addLayout(storage_form)
        content_layout.addWidget(storage_card)

        matching_card = Card(
            "Face matching",
            "Thresholds are deployment-specific. Calibrate them against consented validation data.",
        )
        matching_form = QFormLayout()
        matching_form.setSpacing(10)

        self.auto_threshold_spin = self._threshold_spin()
        matching_form.addRow("Auto-match threshold", self.auto_threshold_spin)

        self.review_threshold_spin = self._threshold_spin()
        matching_form.addRow("Review threshold", self.review_threshold_spin)

        self.margin_spin = self._threshold_spin()
        matching_form.addRow("Minimum score margin", self.margin_spin)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["top_k", "max", "mean", "centroid"])
        self.strategy_combo.setToolTip(
            "top_k is the recommended default because it tolerates a few weak reference photos "
            "without trusting one lucky similarity score."
        )
        matching_form.addRow("Match strategy", self.strategy_combo)

        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 10)
        matching_form.addRow("Top-K references", self.top_k_spin)
        matching_card.body.addLayout(matching_form)
        content_layout.addWidget(matching_card)

        performance_card = Card(
            "Processing",
            "Choose execution mode and image limits for this computer.",
        )
        performance_form = QFormLayout()
        performance_form.setSpacing(10)

        self.processing_mode_combo = QComboBox()
        self.processing_mode_combo.addItems(["auto", "cpu", "gpu"])
        performance_form.addRow("Processing mode", self.processing_mode_combo)

        self.worker_count_spin = QSpinBox()
        self.worker_count_spin.setRange(1, 32)
        self.worker_count_spin.setToolTip(
            "Saved for future multiprocessing support. The current pipeline does not use this value."
        )
        performance_form.addRow("Worker count", self.worker_count_spin)

        self.max_dimension_spin = QSpinBox()
        self.max_dimension_spin.setRange(512, 16384)
        self.max_dimension_spin.setSingleStep(256)
        performance_form.addRow("Max image dimension", self.max_dimension_spin)
        performance_card.body.addLayout(performance_form)

        worker_note = QLabel(
            "Worker count is currently reserved for future multiprocessing and does not change "
            "today's pipeline speed."
        )
        worker_note.setObjectName("cardHint")
        worker_note.setWordWrap(True)
        performance_card.body.addWidget(worker_note)
        content_layout.addWidget(performance_card)

        behavior_card = Card(
            "Duplicates, cache & diagnostics",
            "Control repeated files and how much diagnostic information the app records.",
        )
        behavior_form = QFormLayout()
        behavior_form.setSpacing(10)

        self.duplicate_policy_combo = QComboBox()
        self.duplicate_policy_combo.addItems(["skip", "keep", "rename"])
        behavior_form.addRow("Duplicate policy", self.duplicate_policy_combo)

        self.phash_spin = QSpinBox()
        self.phash_spin.setRange(0, 64)
        behavior_form.addRow("Perceptual hash distance", self.phash_spin)

        self.cache_checkbox = QCheckBox("Skip unchanged photos when a folder is processed again")
        behavior_form.addRow("Processing cache", self.cache_checkbox)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        behavior_form.addRow("Log detail", self.log_level_combo)
        behavior_card.body.addLayout(behavior_form)
        content_layout.addWidget(behavior_card)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        outer.addWidget(self.status_label)

        button_row = QHBoxLayout()
        reset_btn = QPushButton("Restore defaults")
        reset_btn.setObjectName("ghostButton")
        reset_btn.clicked.connect(self._restore_defaults)
        button_row.addWidget(reset_btn)
        button_row.addStretch(1)

        self.save_btn = QPushButton("Save settings")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setMinimumWidth(140)
        self.save_btn.clicked.connect(self._save)
        button_row.addWidget(self.save_btn)
        outer.addLayout(button_row)

        self._load_into_form(context.settings)

    def _set_status(self, text: str, kind: str = "success") -> None:
        names = {
            "info": "infoBanner",
            "success": "successBanner",
            "warning": "warningBanner",
            "error": "errorBanner",
        }
        self.status_label.setObjectName(names.get(kind, "infoBanner"))
        self.status_label.setText(text)
        self.status_label.show()
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _threshold_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.01)
        spin.setDecimals(3)
        return spin

    def _path_row(self, form: QFormLayout, label: str) -> QLineEdit:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        row.addWidget(edit, stretch=1)

        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._browse(edit))
        row.addWidget(browse)

        container = QWidget()
        container.setLayout(row)
        form.addRow(label, container)
        return edit

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select folder",
            edit.text() or "",
        )
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
        self.max_dimension_spin.setValue(settings.max_image_dimension)

        self.duplicate_policy_combo.setCurrentText(settings.duplicate_policy)
        self.phash_spin.setValue(settings.perceptual_hash_threshold)
        self.cache_checkbox.setChecked(settings.cache_enabled)
        self.log_level_combo.setCurrentText(settings.log_level)

        self.status_label.hide()

    def _save(self) -> None:
        if not self.output_dir_edit.text().strip():
            self._set_status("Output folder cannot be empty.", "warning")
            return
        if not self.models_dir_edit.text().strip():
            self._set_status("Models folder cannot be empty.", "warning")
            return

        if self.review_threshold_spin.value() >= self.auto_threshold_spin.value():
            answer = QMessageBox.question(
                self,
                "Unusual threshold order",
                "The review threshold is normally lower than the auto-match threshold. "
                "This configuration removes or reverses the normal human-review band. "
                "Save it anyway?",
            )
            if answer != QMessageBox.Yes:
                return

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

        self._set_status(
            "Settings saved. Matching, duplicate, cache, and logging changes apply to the next "
            "operation. Database/model path changes require a restart.",
            "success",
        )

    def _restore_defaults(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Restore defaults?",
            "Reset every field to the built-in defaults? Nothing is saved until you click Save settings.",
        )
        if confirm == QMessageBox.Yes:
            self._load_into_form(Settings())
            self._set_status(
                "Built-in defaults loaded into the form. Click Save settings to persist them.",
                "info",
            )

    def on_shown(self) -> None:
        self._load_into_form(self.context.settings)
