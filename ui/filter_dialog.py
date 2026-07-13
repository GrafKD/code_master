"""Диалог настройки фильтра мониторинга CAN."""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.translations import _ as tr
from models.utils import hex_to_int, parse_data_bytes
from ui.hex_edit import HexDataEdit


class FilterDialog(QDialog):
    """Модальное окно с правилами фильтрации CAN-кадров."""

    def __init__(self, rules: List[Dict[str, Any]], enabled: bool, interval_ms: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Настройка фильтра"))
        self.resize(720, 360)
        self._font = QFont("Segoe UI", 9)

        self._rules: List[Dict[str, Any]] = []

        self._enabled_check = QCheckBox(tr("Включить фильтр"))
        self._enabled_check.setFont(self._font)
        self._enabled_check.setChecked(enabled)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(0, 9999)
        self._interval_spin.setValue(interval_ms)
        self._interval_spin.setSuffix(tr(" мс"))
        self._interval_spin.setFont(self._font)

        self._add_button = QPushButton(tr("Добавить правило"))
        self._add_button.setFont(self._font)
        self._add_button.clicked.connect(self._add_rule)
        self._remove_button = QPushButton(tr("Удалить правило"))
        self._remove_button.setFont(self._font)
        self._remove_button.clicked.connect(self._remove_rule)

        self._rules_container = QWidget()
        self._rules_layout = QVBoxLayout(self._rules_container)
        self._rules_layout.setSpacing(4)
        self._rules_layout.setContentsMargins(0, 0, 0, 0)
        self._rules_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rules_container)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self._enabled_check)
        top_layout.addWidget(QLabel(tr("Интервал подсветки новых пакетов")))
        top_layout.addWidget(self._interval_spin)
        top_layout.addStretch()
        top_layout.addWidget(self._add_button)
        top_layout.addWidget(self._remove_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        layout.addWidget(scroll)
        layout.addWidget(buttons)

        for rule in rules:
            self._add_rule_widget(rule)
        if not self._rules:
            self._add_rule()

    def _add_rule(self) -> None:
        self._add_rule_widget({"id": "", "from": "", "to": ""})

    def _add_rule_widget(self, rule: Dict[str, Any]) -> None:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        id_edit = QLineEdit()
        id_edit.setFixedWidth(90)
        id_edit.setFont(self._font)
        id_edit.setMaxLength(8)
        id_edit.setPlaceholderText(tr("ID"))
        id_edit.setText(str(rule.get("id", "")))

        from_edits: List[QLineEdit] = []
        to_edits: List[QLineEdit] = []
        for i in range(8):
            fe = HexDataEdit(f"F{i}")
            fe.setFixedWidth(32)
            fe.setFont(self._font)
            from_edits.append(fe)
            te = HexDataEdit(f"T{i}")
            te.setFixedWidth(32)
            te.setFont(self._font)
            to_edits.append(te)
        for fe in from_edits:
            fe.set_siblings(from_edits)
        for te in to_edits:
            te.set_siblings(to_edits)

        from_values = parse_data_bytes(str(rule.get("from", "")).split())
        to_values = parse_data_bytes(str(rule.get("to", "")).split())
        for i, edit in enumerate(from_edits):
            edit.setText(f"{from_values[i]:02X}" if i < len(from_values) else "")
        for i, edit in enumerate(to_edits):
            edit.setText(f"{to_values[i]:02X}" if i < len(to_values) else "")

        row.addWidget(QLabel(tr("ID")))
        row.addWidget(id_edit)
        row.addWidget(QLabel(tr("От")))
        for edit in from_edits:
            row.addWidget(edit)
        row.addWidget(QLabel(tr("До")))
        for edit in to_edits:
            row.addWidget(edit)
        row.addStretch()

        self._rules_layout.insertWidget(self._rules_layout.count() - 1, widget)
        self._rules.append({
            "widget": widget,
            "id": id_edit,
            "from": from_edits,
            "to": to_edits,
        })

    def _remove_rule(self) -> None:
        if not self._rules:
            return
        rule = self._rules.pop()
        rule["widget"].deleteLater()

    def get_result(self) -> Optional[Dict[str, Any]]:
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        rules: List[Dict[str, Any]] = []
        for rule in self._rules:
            can_id = hex_to_int(rule["id"].text())
            from_bytes = bytes(parse_data_bytes([e.text() for e in rule["from"]]))
            to_bytes = bytes(parse_data_bytes([e.text() for e in rule["to"]]))
            rules.append({"id": can_id, "from": from_bytes, "to": to_bytes})
        return {
            "enabled": self._enabled_check.isChecked(),
            "interval_ms": self._interval_spin.value(),
            "rules": rules,
        }
