from ui import QtWidgets
from core.config_validator import ConfigValidator
from core.logger import get_logger
from ui.log_panel import LogViewer

_SOURCE = "LogTab"


class LogTab:

    def __init__(self, logger=None):
        self.log = logger or get_logger()
        self.validate_btn = None
        self.status_label = None
        self.viewer = None

    def build_ui(self):
        widget = QtWidgets.QWidget()
        widget.setObjectName("logTab")
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        validation_group = QtWidgets.QGroupBox("Config Validation")
        validation_layout = QtWidgets.QVBoxLayout(validation_group)
        validation_layout.setSpacing(8)
        validation_layout.setContentsMargins(12, 14, 12, 12)

        hint = QtWidgets.QLabel(
            "Validate all JSON config attribute spelling against actual Maya node "
            "types. Renderers without an installed plugin are skipped automatically. "
            "Validation details are written to the log table below."
        )
        hint.setWordWrap(True)
        validation_layout.addWidget(hint)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.validate_btn = QtWidgets.QPushButton("Validate All JSON Configs")
        self.validate_btn.setObjectName("convertBtn")
        self.validate_btn.setMinimumHeight(32)
        self.validate_btn.clicked.connect(self._run_validation)
        btn_row.addStretch()
        btn_row.addWidget(self.validate_btn)
        validation_layout.addLayout(btn_row)

        self.status_label = QtWidgets.QLabel("Last run: -")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("debugStatus")
        validation_layout.addWidget(self.status_label)

        layout.addWidget(validation_group, stretch=0)

        self.viewer = LogViewer(self.log)
        layout.addWidget(self.viewer, stretch=3)

        return widget

    def set_active(self, active):
        if self.viewer:
            self.viewer.set_active(active)

    def _run_validation(self):
        self.validate_btn.setEnabled(False)
        self.log.info("Running JSON config validation in Maya...", source=_SOURCE)
        try:
            validator = ConfigValidator(logger=self.log)
            _, summary = validator.validate_all()
            self.status_label.setText(
                f"Last run: {summary['ok']} OK, {summary['error']} ERROR, "
                f"{summary['warn']} WARN, {summary['skip']} SKIP, "
                f"{summary['info']} INFO ({summary['total']} checks). "
                f"Details in the log table below."
            )
            self.log.info(
                f"--- DONE: {summary['ok']} OK, {summary['error']} ERROR, "
                f"{summary['warn']} WARN, {summary['skip']} SKIP "
                f"({summary['total']} checks) ---",
                source=_SOURCE,
            )
            if summary["skip"]:
                self.log.warn(
                    f"{summary['skip']} item(s) skipped (missing renderer / empty "
                    "mapping / common placeholder) - not errors.",
                    source=_SOURCE,
                )
            if self.viewer:
                self.viewer.apply_preset("validation")
        finally:
            self.validate_btn.setEnabled(True)
