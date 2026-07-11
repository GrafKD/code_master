"""Страница «Триггеры» с 10 расширенными блоками условий и ответов."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.can_protocol import pack_can_frame
from core.serial_manager import SerialManager
from models.config import Config
from models.logger import get_logger
from models.translations import _ as tr
from models.utils import hex_to_int, int_to_hex, parse_data_bytes

logger = get_logger(__name__)

TRIGGER_COUNT = 10
EXTRA_ROWS = 5
CACHE_ROWS = 5
CHANNELS = [tr("CAN1"), tr("CAN2"), tr("CAN1 и CAN2")]
BIT_RATES = [tr("29 бит"), tr("11 бит")]


class CanTriggerTab(QWidget):
    """Страница управления триггерами CAN."""

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._config = Config()
        self._active = False
        self._internal_triggers: List[Dict[str, object]] = []
        self._trigger_counters = [0] * TRIGGER_COUNT
        self._blocks: List[Dict[str, Any]] = []

        self._create_widgets()
        self._build_layout()
        self._load_config()

    def _make_id_edit(self, font: QFont, placeholder: str = "ID") -> QLineEdit:
        edit = QLineEdit()
        edit.setFixedWidth(80)
        edit.setFont(font)
        edit.setMaxLength(8)
        edit.setPlaceholderText(placeholder)
        return edit

    def _make_data_edits(self, font: QFont) -> List[QLineEdit]:
        edits: List[QLineEdit] = []
        for d in range(8):
            edit = QLineEdit()
            edit.setFixedWidth(30)
            edit.setFont(font)
            edit.setMaxLength(2)
            edit.setPlaceholderText(f"D{d}")
            edits.append(edit)
        return edits

    def _make_channel_combo(self, font: QFont) -> QComboBox:
        combo = QComboBox()
        combo.setFont(font)
        combo.addItems(CHANNELS)
        combo.setFixedWidth(110)
        return combo

    def _make_count_spin(self, font: QFont, max_value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, max_value)
        spin.setValue(1)
        spin.setSuffix(tr(" шт"))
        spin.setFont(font)
        spin.setFixedWidth(70)
        return spin

    def _make_row_widget(
        self,
        font: QFont,
        label: str,
        max_count: int,
    ) -> Dict[str, Any]:
        layout = QHBoxLayout()
        layout.setSpacing(4)
        layout.addWidget(QLabel(label))
        channel = self._make_channel_combo(font)
        layout.addWidget(channel)
        layout.addWidget(QLabel("ID:"))
        can_id = self._make_id_edit(font)
        layout.addWidget(can_id)
        layout.addWidget(QLabel("Data:"))
        data = self._make_data_edits(font)
        for edit in data:
            layout.addWidget(edit)
        count = self._make_count_spin(font, max_count)
        layout.addWidget(count)
        layout.addStretch()
        return {
            "layout": layout,
            "channel": channel,
            "id": can_id,
            "data": data,
            "count": count,
        }

    def _create_widgets(self) -> None:
        font = QFont("Segoe UI", 9)

        self._apply_button = QPushButton(tr("Применить триггеры"))
        self._apply_button.setFixedSize(140, 32)
        self._apply_button.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._apply_button.clicked.connect(self._apply_triggers)

        self._save_button = QPushButton(tr("Сохранить триггеры"))
        self._save_button.setFixedSize(140, 32)
        self._save_button.setFont(QFont("Segoe UI", 10))
        self._save_button.clicked.connect(self._save_triggers)

        self._load_button = QPushButton(tr("Загрузить триггеры"))
        self._load_button.setFixedSize(150, 32)
        self._load_button.setFont(QFont("Segoe UI", 10))
        self._load_button.clicked.connect(self._load_triggers)

        for i in range(TRIGGER_COUNT):
            group = QGroupBox(tr("Триггер {0}").format(i + 1))
            group.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

            active = QCheckBox(tr("Активен"))
            active.setFont(font)

            cache = QCheckBox(tr("Автоматическая запись Data в Кэш"))
            cache.setFont(font)
            cache.stateChanged.connect(lambda state, idx=i: self._on_cache_changed(idx, state))

            counter = QLabel(tr("Срабатываний: 0"))
            counter.setFont(font)

            test_btn = QPushButton(tr("Тест"))
            test_btn.setFixedSize(60, 26)
            test_btn.setFont(font)
            test_btn.clicked.connect(lambda _=False, idx=i: self._on_test(idx))

            bit_combo = QComboBox()
            bit_combo.setFont(font)
            bit_combo.addItems(BIT_RATES)
            bit_combo.setFixedWidth(90)

            data_from = QLineEdit()
            data_from.setFixedWidth(30)
            data_from.setFont(font)
            data_from.setMaxLength(2)
            data_from.setPlaceholderText(tr("от"))

            data_to = QLineEdit()
            data_to.setFixedWidth(30)
            data_to.setFont(font)
            data_to.setMaxLength(2)
            data_to.setPlaceholderText(tr("до"))

            recv_row = self._make_row_widget(font, tr("Приём"), 64)
            resp_row = self._make_row_widget(font, tr("Ответ"), 64)
            resp_row["count"].setRange(1, 64)
            resp_row["count"].setValue(1)

            packet_count = QSpinBox()
            packet_count.setRange(1, 64)
            packet_count.setValue(1)
            packet_count.setSuffix(tr(" шт"))
            packet_count.setFont(font)
            packet_count.setFixedWidth(80)

            extra_rows: List[Dict[str, Any]] = []
            for _ in range(EXTRA_ROWS):
                extra_rows.append(self._make_row_widget(font, "", 64))

            cache_rows: List[Dict[str, Any]] = []
            for _ in range(CACHE_ROWS):
                cache_rows.append(self._make_row_widget(font, "", 0))

            block = {
                "group": group,
                "active": active,
                "cache": cache,
                "counter": counter,
                "test_btn": test_btn,
                "bit_combo": bit_combo,
                "data_from": data_from,
                "data_to": data_to,
                "recv_row": recv_row,
                "resp_row": resp_row,
                "packet_count": packet_count,
                "extra_rows": extra_rows,
                "cache_rows": cache_rows,
            }
            self._blocks.append(block)

    def _build_layout(self) -> None:
        font = QFont("Segoe UI", 9)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(10)
        container_layout.setContentsMargins(8, 8, 8, 8)

        for block in self._blocks:
            group_layout = QVBoxLayout(block["group"])
            group_layout.setSpacing(5)
            group_layout.setContentsMargins(6, 6, 6, 6)

            top = QHBoxLayout()
            top.addWidget(block["active"])
            top.addWidget(block["cache"])
            top.addStretch()
            top.addWidget(block["counter"])
            top.addWidget(block["test_btn"])
            group_layout.addLayout(top)

            bit_layout = QHBoxLayout()
            bit_layout.setSpacing(4)
            bit_layout.addWidget(QLabel(tr("Бит:")))
            bit_layout.addWidget(block["bit_combo"])
            bit_layout.addWidget(QLabel("Data"))
            bit_layout.addWidget(block["data_from"])
            bit_layout.addWidget(QLabel("-"))
            bit_layout.addWidget(block["data_to"])
            bit_layout.addStretch()
            group_layout.addLayout(bit_layout)

            group_layout.addLayout(block["recv_row"]["layout"])
            group_layout.addLayout(block["resp_row"]["layout"])

            count_layout = QHBoxLayout()
            count_layout.addWidget(QLabel(tr("Кол-во отправляемых пакетов:")))
            count_layout.addWidget(block["packet_count"])
            count_layout.addStretch()
            group_layout.addLayout(count_layout)

            group_layout.addWidget(QLabel(tr("Дополнительные ответы:")))
            for row in block["extra_rows"]:
                group_layout.addLayout(row["layout"])

            group_layout.addWidget(QLabel(tr("Кэш:")))
            for row in block["cache_rows"]:
                group_layout.addLayout(row["layout"])
            self._set_cache_rows_enabled(block, False)

            container_layout.addWidget(block["group"])

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self._apply_button)
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._load_button)
        buttons.addStretch()
        container_layout.addLayout(buttons)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _on_cache_changed(self, index: int, state: int) -> None:
        enabled = state == Qt.CheckState.Checked.value
        block = self._blocks[index]
        self._set_response_enabled(block, not enabled)
        self._set_cache_rows_enabled(block, enabled)

    def _set_response_enabled(self, block: Dict[str, Any], enabled: bool) -> None:
        block["resp_row"]["channel"].setEnabled(enabled)
        block["resp_row"]["id"].setEnabled(enabled)
        for edit in block["resp_row"]["data"]:
            edit.setEnabled(enabled)
        block["resp_row"]["count"].setEnabled(enabled)
        block["packet_count"].setEnabled(enabled)
        for row in block["extra_rows"]:
            row["channel"].setEnabled(enabled)
            row["id"].setEnabled(enabled)
            for edit in row["data"]:
                edit.setEnabled(enabled)
            row["count"].setEnabled(enabled)

    def _set_cache_rows_enabled(self, block: Dict[str, Any], enabled: bool) -> None:
        for row in block["cache_rows"]:
            row["channel"].setEnabled(enabled)
            row["id"].setEnabled(enabled)
            for edit in row["data"]:
                edit.setEnabled(enabled)
            row["count"].setEnabled(enabled)

    def _parse_id(self, text: str) -> Optional[int]:
        return hex_to_int(text.strip())

    def _parse_data(self, edits: List[QLineEdit]) -> List[Optional[int]]:
        result: List[Optional[int]] = []
        for edit in edits:
            text = edit.text().strip()
            if text:
                val = hex_to_int(text)
                result.append(val if val is not None else 0)
            else:
                result.append(None)
        return result

    def _build_internal_triggers(self) -> List[Dict[str, Any]]:
        triggers = []
        for i, block in enumerate(self._blocks):
            if not block["active"].isChecked():
                continue
            recv_id = self._parse_id(block["recv_row"]["id"].text())
            if recv_id is None:
                continue
            triggers.append({
                "index": i,
                "recv_id": recv_id,
                "recv_data": self._parse_data(block["recv_row"]["data"]),
                "recv_channel": block["recv_row"]["channel"].currentIndex(),
                "data_from": self._parse_id(block["data_from"].text()),
                "data_to": self._parse_id(block["data_to"].text()),
                "cache": block["cache"].isChecked(),
                "responses": self._collect_rows([block["resp_row"]] + block["extra_rows"]),
                "cache_rows": self._collect_rows(block["cache_rows"]),
                "packet_count": block["packet_count"].value(),
            })
        return triggers

    def _collect_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for row in rows:
            can_id = self._parse_id(row["id"].text())
            if can_id is None:
                continue
            result.append({
                "channel": row["channel"].currentIndex(),
                "id": can_id,
                "data": self._parse_data(row["data"]),
                "count": row["count"].value(),
            })
        return result

    def _apply_triggers(self) -> None:
        self._internal_triggers = self._build_internal_triggers()
        self._active = bool(self._internal_triggers)
        logger.info("Триггеры применены: %d активных", len(self._internal_triggers))
        QMessageBox.information(self, tr("Готово"), tr("Триггеры применены: {0}").format(len(self._internal_triggers)))

    def _load_config(self) -> None:
        triggers = self._config.get("triggers", [])
        self.set_config(triggers if isinstance(triggers, list) else [])

    def _save_config(self) -> None:
        self._config.set("triggers", self._collect_config())

    def _collect_config(self) -> List[Dict[str, object]]:
        config = []
        for block in self._blocks:
            config.append({
                "active": block["active"].isChecked(),
                "cache": block["cache"].isChecked(),
                "bit": block["bit_combo"].currentIndex(),
                "data_from": block["data_from"].text(),
                "data_to": block["data_to"].text(),
                "recv_id": block["recv_row"]["id"].text(),
                "recv_data": " ".join(e.text() for e in block["recv_row"]["data"] if e.text()),
                "recv_channel": block["recv_row"]["channel"].currentIndex(),
                "resp_id": block["resp_row"]["id"].text(),
                "resp_data": " ".join(e.text() for e in block["resp_row"]["data"] if e.text()),
                "resp_channel": block["resp_row"]["channel"].currentIndex(),
                "resp_count": block["resp_row"]["count"].value(),
                "packet_count": block["packet_count"].value(),
                "extra_rows": [
                    {
                        "channel": row["channel"].currentIndex(),
                        "id": row["id"].text(),
                        "data": " ".join(e.text() for e in row["data"] if e.text()),
                        "count": row["count"].value(),
                    }
                    for row in block["extra_rows"]
                ],
                "cache_rows": [
                    {
                        "channel": row["channel"].currentIndex(),
                        "id": row["id"].text(),
                        "data": " ".join(e.text() for e in row["data"] if e.text()),
                        "count": row["count"].value(),
                    }
                    for row in block["cache_rows"]
                ],
            })
        return config

    def set_config(self, triggers: List[Dict[str, object]]) -> None:
        """Загружает конфигурацию триггеров из списка."""
        for i, block in enumerate(self._blocks):
            trigger = triggers[i] if i < len(triggers) else {}
            block["active"].setChecked(trigger.get("active", False))
            block["cache"].setChecked(trigger.get("cache", False))
            block["bit_combo"].setCurrentIndex(int(trigger.get("bit", 0)))
            block["data_from"].setText(str(trigger.get("data_from", "")))
            block["data_to"].setText(str(trigger.get("data_to", "")))

            self._set_row(block["recv_row"], trigger, "recv_id", "recv_data", "recv_channel")
            self._set_row(block["resp_row"], trigger, "resp_id", "resp_data", "resp_channel", count_key="resp_count")
            block["packet_count"].setValue(int(trigger.get("packet_count", 1)))

            for r, row in enumerate(block["extra_rows"]):
                key = "extra_rows"
                rows = trigger.get(key, [])
                if r < len(rows):
                    self._set_row(row, rows[r], "id", "data", "channel", count_key="count")

            for r, row in enumerate(block["cache_rows"]):
                rows = trigger.get("cache_rows", [])
                if r < len(rows):
                    self._set_row(row, rows[r], "id", "data", "channel", count_key="count")

            self._on_cache_changed(i, Qt.CheckState.Checked.value if block["cache"].isChecked() else Qt.CheckState.Unchecked.value)

    def _set_row(
        self,
        row: Dict[str, Any],
        data: Dict[str, object],
        id_key: str,
        data_key: str,
        channel_key: str,
        count_key: Optional[str] = None,
    ) -> None:
        row["id"].setText(str(data.get(id_key, "")))
        bytes_data = parse_data_bytes(str(data.get(data_key, "")).split())
        for d, edit in enumerate(row["data"]):
            edit.setText(f"{bytes_data[d]:02X}" if d < len(bytes_data) else "")
        row["channel"].setCurrentIndex(int(data.get(channel_key, 0)))
        if count_key is not None:
            row["count"].setValue(int(data.get(count_key, 1)))

    def _save_triggers(self) -> None:
        self._save_config()
        path, _ = QFileDialog.getSaveFileName(self, tr("Сохранить триггеры"), "", "JSON files (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self._collect_config(), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Триггеры сохранены в %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка сохранения триггеров: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось сохранить триггеры: {0}").format(exc))

    def _load_triggers(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Загрузить триггеры"), "", "JSON files (*.json)")
        if not path:
            return
        try:
            triggers = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(triggers, list):
                raise ValueError(tr("Файл должен содержать список триггеров"))
            self.set_config(triggers)
            self._save_config()
            logger.info("Триггеры загружены из %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка загрузки триггеров: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось загрузить триггеры: {0}").format(exc))

    def _on_test(self, index: int) -> None:
        """Тестирует отправку ответов для блока без проверки условия."""
        if index >= len(self._blocks):
            return
        block = self._blocks[index]
        rows = block["cache_rows"] if block["cache"].isChecked() else [block["resp_row"]] + block["extra_rows"]
        for row in rows:
            can_id = self._parse_id(row["id"].text())
            if can_id is None:
                continue
            data = self._data_from_edits(row["data"])
            count = row["count"].value()
            self._send_frame(can_id, data, row["channel"].currentIndex(), count)
        logger.info("Тест триггера %d выполнен", index + 1)

    def _data_from_edits(self, edits: List[QLineEdit]) -> bytes:
        parsed = self._parse_data(edits)
        data = bytearray(8)
        for idx, val in enumerate(parsed):
            if val is not None and idx < 8:
                data[idx] = val & 0xFF
        return bytes(data)

    def _send_frame(self, can_id: int, data: bytes, channel_index: int, count: int) -> None:
        if not self._serial_manager.is_open():
            return
        for _ in range(count):
            if channel_index == 0:
                frame = pack_can_frame(1, can_id, data)
                self._serial_manager.send_data(frame)
            elif channel_index == 1:
                frame = pack_can_frame(2, can_id, data)
                self._serial_manager.send_data(frame)
            else:
                self._serial_manager.send_data(pack_can_frame(1, can_id, data))
                self._serial_manager.send_data(pack_can_frame(2, can_id, data))

    def process_frame(self, frame: Dict[str, Any]) -> None:
        if not self._active:
            return
        frame_id = int(frame["id"])
        frame_channel = int(frame["channel"])
        data = bytes(frame["data"])

        for trigger in self._internal_triggers:
            if not self._match_condition(trigger, frame_id, frame_channel, data):
                continue
            idx = int(trigger["index"])
            self._trigger_counters[idx] += 1
            self._blocks[idx]["counter"].setText(tr("Срабатываний: {0}").format(self._trigger_counters[idx]))

            rows = trigger["cache_rows"] if trigger["cache"] else trigger["responses"]
            for row in rows:
                row_data = bytearray(8)
                for b, val in enumerate(row["data"]):
                    if val is not None and b < 8:
                        row_data[b] = val & 0xFF
                self._send_frame(row["id"], bytes(row_data), row["channel"], row["count"])
            break

    def _match_condition(
        self,
        trigger: Dict[str, Any],
        frame_id: int,
        frame_channel: int,
        data: bytes,
    ) -> bool:
        if trigger["recv_id"] != frame_id:
            return False
        recv_channel = int(trigger["recv_channel"])
        if recv_channel != 2 and recv_channel + 1 != frame_channel:
            return False
        for idx, expected in enumerate(trigger["recv_data"]):
            if expected is None:
                continue
            if idx >= len(data) or data[idx] != expected:
                return False
        if data and trigger["data_from"] is not None and trigger["data_to"] is not None:
            if not (trigger["data_from"] <= data[0] <= trigger["data_to"]):
                return False
        return True

    def create_trigger_from_packet(self, packet: Dict[str, object]) -> None:
        """Создаёт первый триггер из пакета мониторинга."""
        if not self._blocks:
            return
        block = self._blocks[0]
        block["active"].setChecked(True)
        can_id = int(packet["id"])
        block["recv_row"]["id"].setText(int_to_hex(can_id, 8 if can_id > 0x7FF else 3))
        bytes_data = bytes(packet["data"])
        for d, edit in enumerate(block["recv_row"]["data"]):
            edit.setText(f"{bytes_data[d]:02X}" if d < len(bytes_data) else "")
        logger.info("Триггер создан из пакета ID=0x%X", can_id)
