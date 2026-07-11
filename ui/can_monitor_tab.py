"""Вкладка «Мониторинг CAN» с продвинутыми функциями анализа."""

import csv
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TextIO, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.can_protocol import MARKER_TX_EXT, pack_can_frame
from core.dbc_manager import DBCManager
from core.dbc_parser import decode_frame
from core.serial_manager import SerialManager
from models.logger import get_logger
from models.translations import _ as tr
from models.utils import bytes_to_hex_string, format_data_bytes, hex_to_int, int_to_hex, parse_data_bytes

logger = get_logger(__name__)

MAX_TABLE_ROWS = 50_000
HIGHLIGHT_COLOR = "#4A6A8A"
HIGHLIGHT_MS = 2000


def _ascii_from_data(data: bytes) -> str:
    """Возвращает печатные ASCII-символы для байт, непечатные заменяются на '.'."""
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


class DataVariantsDialog(QDialog):
    """Диалог со списком уникальных наборов данных для выбранного ID."""

    def __init__(self, can_id: int, variants: Set[bytes], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Варианты данных для ID {0}").format(int_to_hex(can_id, 8 if can_id > 0x7FF else 3)))
        self.resize(500, 300)
        layout = QVBoxLayout(self)
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels([tr("№"), tr("Данные"), tr("ASCII")])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, data in enumerate(sorted(variants)):
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self._table.setItem(row, 1, QTableWidgetItem(" ".join(f"{b:02X}" for b in data)))
            self._table.setItem(row, 2, QTableWidgetItem(_ascii_from_data(data)))
        layout.addWidget(self._table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class BitmapDialog(QDialog):
    """Диалог с битовой картой 8×8 для последнего кадра ID."""

    def __init__(self, can_id: int, data: bytes, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Битовая карта ID {0}").format(int_to_hex(can_id, 8 if can_id > 0x7FF else 3)))
        layout = QGridLayout(self)
        for byte_idx in range(8):
            byte = data[byte_idx] if byte_idx < len(data) else 0
            for bit in range(8):
                label = QLabel("1" if (byte >> bit) & 1 else "0")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet(
                    f"background-color: {'#4A6A8A' if (byte >> bit) & 1 else '#2B2B2B'}; "
                    "border: 1px solid #555; min-width: 22px; min-height: 22px;"
                )
                # little-endian bit order: bit 0 = LSB
                layout.addWidget(label, byte_idx, 7 - bit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons, 8, 0, 1, 8)


class DbcSignalDialog(QDialog):
    """Диалог выбора сообщения и сигнала из DBC для автозаполнения."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Выбор сигнала из DBC"))
        self.resize(360, 180)
        self._dbc_manager = DBCManager()
        self._result: Optional[Tuple[int, List[int]]] = None
        layout = QVBoxLayout(self)
        self._message_combo = QComboBox()
        self._signal_combo = QComboBox()
        self._message_combo.currentIndexChanged.connect(self._on_message_changed)
        layout.addWidget(QLabel(tr("Сообщение:")))
        layout.addWidget(self._message_combo)
        layout.addWidget(QLabel(tr("Сигнал:")))
        layout.addWidget(self._signal_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._populate()

    def _populate(self) -> None:
        db = self._dbc_manager.get_cantools_db()
        self._message_combo.clear()
        if db is None:
            return
        for message in db.messages:
            self._message_combo.addItem(message.name, message)
        self._on_message_changed(0)

    def _on_message_changed(self, index: int) -> None:
        self._signal_combo.clear()
        message = self._message_combo.itemData(index)
        if message is None:
            return
        for signal in message.signals:
            self._signal_combo.addItem(signal.name, signal)

    def _on_ok(self) -> None:
        message = self._message_combo.currentData()
        signal = self._signal_combo.currentData()
        if message is None or signal is None:
            self.reject()
            return
        try:
            encoded = message.encode({signal.name: 0})
            self._result = (message.frame_id, list(encoded))
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка кодирования сигнала DBC: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось закодировать сигнал: {0}").format(exc))
            return
        self.accept()

    def get_result(self) -> Optional[Tuple[int, List[int]]]:
        return self._result


class CanChannelMonitor(QWidget):
    """Панель мониторинга одного CAN-канала."""

    create_trigger_requested = Signal(dict)

    def __init__(self, channel: int, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel = channel
        self._channel_byte = channel
        self._serial_manager = serial_manager
        self._running = False
        self._paused = False
        self._unique_mode = True
        self._received_count = 0
        self._packet_times: deque[float] = deque()
        self._manual_send_ids: Set[int] = set()
        self._last_packet_time: Optional[float] = None
        self._send_history: List[Dict[str, object]] = []
        self._dbc_manager = DBCManager()

        # Для режима уникальных ID
        self._id_to_row: Dict[int, int] = {}
        self._id_stats: Dict[int, Dict[str, Any]] = {}
        self._id_data_variants: Dict[int, Set[bytes]] = {}
        self._highlight_timers: Dict[int, QTimer] = {}

        self._create_widgets()
        self._layout_widgets()
        self._setup_timers()

    def _create_widgets(self) -> None:
        font = QFont("Segoe UI", 9)

        self._start_button = QPushButton(tr("Старт"))
        self._start_button.setFixedSize(60, 24)
        self._start_button.setFont(font)
        self._start_button.clicked.connect(self._start)

        self._stop_button = QPushButton(tr("Стоп"))
        self._stop_button.setFixedSize(60, 24)
        self._stop_button.setFont(font)
        self._stop_button.clicked.connect(self._stop)

        self._clear_button = QPushButton(tr("Очистить"))
        self._clear_button.setFixedSize(70, 24)
        self._clear_button.setFont(font)
        self._clear_button.clicked.connect(self._clear)

        self._mode_button = QPushButton(tr("Режим: уникальные"))
        self._mode_button.setFixedSize(130, 24)
        self._mode_button.setFont(font)
        self._mode_button.clicked.connect(self._toggle_mode)

        self._filter_from = QLineEdit()
        self._filter_from.setFixedWidth(70)
        self._filter_from.setMaxLength(8)
        self._filter_from.setFont(font)
        self._filter_from.setPlaceholderText(tr("ID от"))

        self._filter_to = QLineEdit()
        self._filter_to.setFixedWidth(70)
        self._filter_to.setMaxLength(8)
        self._filter_to.setFont(font)
        self._filter_to.setPlaceholderText(tr("ID до"))

        self._exclude_edit = QLineEdit()
        self._exclude_edit.setFixedWidth(120)
        self._exclude_edit.setFont(font)
        self._exclude_edit.setPlaceholderText(tr("Исключить ID"))
        self._exclude_edit.textChanged.connect(self._apply_filters)

        self._known_only_check = QCheckBox(tr("Только известные ID"))
        self._known_only_check.setFont(font)
        self._known_only_check.stateChanged.connect(self._apply_filters)

        self._pause_check = QCheckBox(tr("Приостановить"))
        self._pause_check.setFont(font)
        self._pause_check.stateChanged.connect(self._on_pause_changed)

        self._search_edit = QLineEdit()
        self._search_edit.setFixedWidth(160)
        self._search_edit.setFont(font)
        self._search_edit.setPlaceholderText(tr("Поиск по ID или данным…"))
        self._search_edit.textChanged.connect(self._apply_search)

        self._export_button = QPushButton(tr("Экспорт"))
        self._export_button.setFixedSize(80, 24)
        self._export_button.setFont(font)
        self._export_button.setMenu(self._build_export_menu())

        self._table = QTableWidget()
        self._table.setColumnCount(15)
        self._table.setHorizontalHeaderLabels(
            [
                tr("Время"), "ID", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
                tr("DLC"), tr("Период"), tr("Счётчик"), tr("ASCII"), tr("Сигналы"),
            ]
        )
        self._table.setColumnHidden(0, True)
        self._table.horizontalHeader().setSectionHidden(0, True)
        self._table.setFont(font)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self._send_id_edit = QLineEdit()
        self._send_id_edit.setFixedWidth(80)
        self._send_id_edit.setMaxLength(8)
        self._send_id_edit.setFont(font)
        self._send_id_edit.setPlaceholderText("ID")

        self._send_data_edits: List[QLineEdit] = []
        for i in range(8):
            edit = QLineEdit()
            edit.setFixedWidth(30)
            edit.setFont(font)
            edit.setMaxLength(2)
            edit.setPlaceholderText(f"D{i}")
            self._send_data_edits.append(edit)

        self._send_from_dbc_button = QPushButton(tr("Из DBC"))
        self._send_from_dbc_button.setFixedSize(70, 24)
        self._send_from_dbc_button.setFont(font)
        self._send_from_dbc_button.clicked.connect(self._on_send_from_dbc)

        self._send_history_combo = QComboBox()
        self._send_history_combo.setFixedWidth(150)
        self._send_history_combo.setFont(font)
        self._send_history_combo.activated.connect(self._on_history_activated)
        self._rebuild_history_combo()

        self._cyclic_check = QCheckBox(tr("Циклически"))
        self._cyclic_check.setFont(font)
        self._cyclic_check.stateChanged.connect(self._on_cyclic_changed)

        self._cyclic_interval_edit = QLineEdit()
        self._cyclic_interval_edit.setFixedWidth(50)
        self._cyclic_interval_edit.setMaxLength(5)
        self._cyclic_interval_edit.setFont(font)
        self._cyclic_interval_edit.setText("1000")

        self._send_button = QPushButton(tr("Отправить"))
        self._send_button.setFixedSize(80, 26)
        self._send_button.setFont(font)
        self._send_button.clicked.connect(self._send_manual)

        self._cyclic_timer = QTimer(self)
        self._cyclic_timer.timeout.connect(self._send_cyclic_frame)
        self._cyclic_frame: Optional[bytes] = None

        self._stats_label = QLabel(tr("Принято: 0 | Скорость: 0 пак/с"))
        self._stats_label.setFont(font)

    def _build_export_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(tr("Текущую таблицу в CSV"), self._export_current_table)
        menu.addAction(tr("Поток в CSV"), self._export_stream_csv)
        menu.addAction(tr("Трассировка (CarBus формат)"), self._export_carbus_trace)
        return menu

    def _layout_widgets(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(4, 4, 4, 4)

        control_layout = QGridLayout()
        control_layout.setSpacing(4)
        control_layout.addWidget(self._start_button, 0, 0)
        control_layout.addWidget(self._stop_button, 0, 1)
        control_layout.addWidget(self._clear_button, 0, 2)
        control_layout.addWidget(self._mode_button, 0, 3)
        control_layout.addWidget(QLabel(tr("ID от")), 0, 4)
        control_layout.addWidget(self._filter_from, 0, 5)
        control_layout.addWidget(QLabel(tr("до")), 0, 6)
        control_layout.addWidget(self._filter_to, 0, 7)
        control_layout.addWidget(QLabel(tr("Искл.")), 0, 8)
        control_layout.addWidget(self._exclude_edit, 0, 9)
        control_layout.addWidget(self._known_only_check, 1, 0, 1, 2)
        control_layout.addWidget(self._pause_check, 1, 2, 1, 2)
        control_layout.addWidget(QLabel(tr("Поиск:")), 1, 4)
        control_layout.addWidget(self._search_edit, 1, 5, 1, 3)
        control_layout.addWidget(self._export_button, 1, 8, 1, 2)
        layout.addLayout(control_layout)

        layout.addWidget(self._table, 1)

        send_layout = QGridLayout()
        send_layout.setSpacing(4)
        send_layout.addWidget(QLabel(tr("Отправить:")), 0, 0)
        send_layout.addWidget(self._send_id_edit, 0, 1)
        for idx, edit in enumerate(self._send_data_edits):
            send_layout.addWidget(edit, 0, 2 + idx)
        send_layout.addWidget(self._send_from_dbc_button, 0, 10)
        send_layout.addWidget(self._send_button, 0, 11)
        send_layout.addWidget(self._send_history_combo, 0, 12, 1, 2)
        send_layout.addWidget(self._cyclic_check, 1, 1)
        send_layout.addWidget(QLabel(tr("интервал мс:")), 1, 2)
        send_layout.addWidget(self._cyclic_interval_edit, 1, 3)
        send_layout.setColumnStretch(13, 1)
        layout.addLayout(send_layout)

        layout.addWidget(self._stats_label)

    def _setup_timers(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_stats)
        self._timer.start(1000)
        self._activity_timer = QTimer(self)
        self._activity_timer.timeout.connect(self._update_activity_color)
        self._activity_timer.start(500)

    def _update_activity_color(self) -> None:
        if self._last_packet_time is None:
            color = "#2B2B2B"
        elif time.time() - self._last_packet_time > 1.0:
            color = "#3A2020"
        else:
            color = "#1A3A1A"
        self.setStyleSheet(f"CanChannelMonitor {{ background-color: {color}; border-radius: 6px; }}")

    def _toggle_mode(self) -> None:
        self._unique_mode = not self._unique_mode
        self._mode_button.setText(tr("Режим: уникальные") if self._unique_mode else tr("Режим: поток"))
        self._clear()

    def _start(self) -> None:
        self._running = True
        logger.info("Мониторинг CAN%d запущен", self._channel)

    def _stop(self) -> None:
        self._running = False
        self._stop_cyclic_timer()
        logger.info("Мониторинг CAN%d остановлен", self._channel)

    def _clear(self) -> None:
        self._table.setRowCount(0)
        self._id_to_row.clear()
        self._id_stats.clear()
        self._id_data_variants.clear()
        for timer in self._highlight_timers.values():
            timer.stop()
        self._highlight_timers.clear()
        self._received_count = 0
        self._packet_times.clear()
        self._last_packet_time = None
        self._stats_label.setText(tr("Принято: 0 | Скорость: 0 пак/с"))
        self._update_activity_color()

    def _on_pause_changed(self, state: int) -> None:
        self._paused = state == Qt.CheckState.Checked.value

    def _filter_range(self) -> Tuple[Optional[int], Optional[int]]:
        return (hex_to_int(self._filter_from.text()), hex_to_int(self._filter_to.text()))

    def _exclude_ids(self) -> Set[int]:
        ids: Set[int] = set()
        for token in self._exclude_edit.text().replace(",", " ").split():
            value = hex_to_int(token)
            if value is not None:
                ids.add(value)
        return ids

    def _apply_filters(self) -> None:
        f_from, f_to = self._filter_range()
        exclude = self._exclude_ids()
        known_only = self._known_only_check.isChecked()
        for row in range(self._table.rowCount()):
            hidden = False
            id_item = self._table.item(row, 1)
            if id_item is not None:
                can_id = hex_to_int(id_item.text())
                if can_id is not None:
                    if f_from is not None and can_id < f_from:
                        hidden = True
                    if f_to is not None and can_id > f_to:
                        hidden = True
                    if can_id in exclude:
                        hidden = True
                    if known_only and not self._dbc_manager.get_message(can_id):
                        hidden = True
            self._table.setRowHidden(row, hidden)

    def _apply_search(self, text: str = "") -> None:
        query = text.strip().lower()
        if not query:
            for row in range(self._table.rowCount()):
                self._table.setRowHidden(row, False)
            self._apply_filters()
            return
        for row in range(self._table.rowCount()):
            hidden = True
            for col in range(1, 15):
                item = self._table.item(row, col)
                if item is not None and query in item.text().lower():
                    hidden = False
                    break
            self._table.setRowHidden(row, hidden)

    def _send_manual(self) -> None:
        can_id = hex_to_int(self._send_id_edit.text())
        if can_id is None:
            return
        data = parse_data_bytes([edit.text() for edit in self._send_data_edits])
        self._cyclic_frame = pack_can_frame(self._channel_byte, can_id, bytes(data))
        if self._send_cyclic_frame():
            self._add_to_history(can_id, data)
        if self._cyclic_check.isChecked():
            self._start_cyclic_timer()

    def _on_send_from_dbc(self) -> None:
        dialog = DbcSignalDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.get_result()
        if result is None:
            return
        can_id, data = result
        self._send_id_edit.setText(int_to_hex(can_id, 8 if can_id > 0x7FF else 3))
        for i, edit in enumerate(self._send_data_edits):
            edit.setText(f"{data[i]:02X}" if i < len(data) else "")

    def _add_to_history(self, can_id: int, data: List[int]) -> None:
        entry = {"id": can_id, "data": data[:8]}
        self._send_history = [e for e in self._send_history if not (e["id"] == can_id and e["data"] == entry["data"])]
        self._send_history.insert(0, entry)
        self._send_history = self._send_history[:10]
        self._rebuild_history_combo()

    def _rebuild_history_combo(self) -> None:
        self._send_history_combo.blockSignals(True)
        self._send_history_combo.clear()
        self._send_history_combo.addItem(tr("— История —"), None)
        for entry in self._send_history:
            id_text = int_to_hex(entry["id"], 8 if entry["id"] > 0x7FF else 3)
            data_text = " ".join(int_to_hex(b, 2) for b in entry["data"])
            self._send_history_combo.addItem(f"ID: {id_text} Data: {data_text}", entry)
        self._send_history_combo.blockSignals(False)

    def _on_history_activated(self, index: int) -> None:
        entry = self._send_history_combo.itemData(index)
        if not isinstance(entry, dict):
            return
        can_id = entry.get("id")
        data = entry.get("data", [])
        if can_id is None:
            return
        self._send_id_edit.setText(int_to_hex(can_id, 8 if can_id > 0x7FF else 3))
        for i, edit in enumerate(self._send_data_edits):
            edit.setText(int_to_hex(data[i], 2) if i < len(data) else "")

    def _start_cyclic_timer(self) -> None:
        try:
            interval_ms = int(self._cyclic_interval_edit.text().strip() or "1000")
        except ValueError:
            interval_ms = 1000
        interval_ms = max(10, interval_ms)
        self._cyclic_timer.start(interval_ms)

    def _stop_cyclic_timer(self) -> None:
        if self._cyclic_timer.isActive():
            self._cyclic_timer.stop()

    def _send_cyclic_frame(self) -> bool:
        if self._cyclic_frame is None:
            return False
        if self._serial_manager.send_data(self._cyclic_frame):
            can_id = int.from_bytes(self._cyclic_frame[2:6], "little") if self._cyclic_frame[0] == MARKER_TX_EXT else (self._cyclic_frame[2] | (self._cyclic_frame[3] << 8))
            self._manual_send_ids.add(can_id)
            return True
        return False

    def _on_cyclic_changed(self, state: int) -> None:
        if state == Qt.CheckState.Checked.value:
            if self._cyclic_frame is not None:
                self._start_cyclic_timer()
        else:
            self._stop_cyclic_timer()

    def _update_stats(self) -> None:
        now = time.time()
        while self._packet_times and now - self._packet_times[0] > 1.0:
            self._packet_times.popleft()
        speed = len(self._packet_times)
        self._stats_label.setText(tr("Принято: {0} | Скорость: {1} пак/с").format(self._received_count, speed))

    def _format_signals(self, can_id: int, data: bytes) -> str:
        db = self._dbc_manager.get_cantools_db()
        if db is None:
            return ""
        decoded = decode_frame(db, can_id, data)
        if decoded is None:
            return ""
        parts = []
        for name, info in list(decoded.items())[:3]:
            if isinstance(info, dict):
                parts.append(f"{name}={info['value']:.2f}{info.get('unit', '')}")
            else:
                parts.append(f"{name}={info}")
        return " | ".join(parts)

    def _format_period(self, can_id: int, now: float) -> str:
        stats = self._id_stats.get(can_id)
        if stats is None or stats.get("last_time") is None:
            return ""
        period_ms = int((now - stats["last_time"]) * 1000)
        return f"{period_ms} мс"

    def _build_row_items(self, frame_id: int, data: bytes, timestamp: str, period: str, count: int) -> List[str]:
        id_width = 8 if frame_id > 0x7FF else 3
        data_hex = format_data_bytes(data) + [""] * (8 - len(data))
        signals = self._format_signals(frame_id, data)
        return [
            timestamp,
            int_to_hex(frame_id, id_width),
            *data_hex[:8],
            str(len(data)),
            period,
            str(count),
            _ascii_from_data(data),
            signals,
        ]

    def _reset_row_highlight(self, row: int) -> None:
        for col in range(2, 10):
            item = self._table.item(row, col)
            if item is not None:
                item.setBackground(QColor())

    def _highlight_changed_bytes(self, row: int, new_data: bytes, old_data: bytes) -> None:
        if row in self._highlight_timers:
            self._highlight_timers[row].stop()
        color = QColor(HIGHLIGHT_COLOR)
        for col in range(2, 10):
            byte_idx = col - 2
            item = self._table.item(row, col)
            if item is None:
                continue
            if byte_idx < len(new_data) and (byte_idx >= len(old_data) or new_data[byte_idx] != old_data[byte_idx]):
                item.setBackground(color)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda r=row: self._reset_row_highlight(r))
        timer.start(HIGHLIGHT_MS)
        self._highlight_timers[row] = timer

    def add_frame(self, frame: Dict[str, object]) -> None:
        if not self._running or self._paused:
            return
        frame_id = int(frame["id"])
        f_from, f_to = self._filter_range()
        exclude = self._exclude_ids()
        if f_from is not None and frame_id < f_from:
            return
        if f_to is not None and frame_id > f_to:
            return
        if frame_id in exclude:
            return
        if self._known_only_check.isChecked() and not self._dbc_manager.get_message(frame_id):
            return

        self._received_count += 1
        self._packet_times.append(time.time())
        self._last_packet_time = time.time()

        data = bytes(frame["data"])
        now = time.time()
        stats = self._id_stats.setdefault(frame_id, {"count": 0, "last_time": None, "last_data": b""})
        stats["count"] += 1
        period = self._format_period(frame_id, now)
        stats["last_time"] = now

        timestamp = time.strftime("%H:%M:%S") + f".{int((now % 1) * 1000):03d}"
        items = self._build_row_items(frame_id, data, timestamp, period, stats["count"])

        tooltip = ""
        if self._dbc_manager.is_loaded():
            tooltip = self._dbc_manager.describe_frame(frame_id, data)

        if self._unique_mode and frame_id in self._id_to_row:
            row = self._id_to_row[frame_id]
            old_data = stats["last_data"]
            for col, text in enumerate(items):
                item = self._table.item(row, col)
                if item is None:
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._table.setItem(row, col, item)
                else:
                    item.setText(text)
                if tooltip:
                    item.setToolTip(tooltip)
            self._highlight_changed_bytes(row, data, old_data)
        else:
            if self._table.rowCount() >= MAX_TABLE_ROWS:
                self._table.removeRow(0)
                if self._unique_mode:
                    # Перестраиваем словарь, так как индексы сместились (редкий случай)
                    self._id_to_row = {}
                    for r in range(self._table.rowCount()):
                        id_item = self._table.item(r, 1)
                        if id_item is not None:
                            fid = hex_to_int(id_item.text())
                            if fid is not None:
                                self._id_to_row[fid] = r
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if tooltip:
                    item.setToolTip(tooltip)
                self._table.setItem(row, col, item)
            if self._unique_mode:
                self._id_to_row[frame_id] = row

        stats["last_data"] = data
        self._id_data_variants.setdefault(frame_id, set()).add(data)

        if frame_id in self._manual_send_ids:
            highlight_color = QColor(HIGHLIGHT_COLOR)
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None:
                    item.setBackground(highlight_color)

        self._table.scrollToBottom()
        if self._search_edit.text().strip():
            self._apply_search(self._search_edit.text())
        else:
            self._apply_filters()

    def _show_context_menu(self, position) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        menu = QMenu(self)
        menu.addAction(tr("Копировать ID"), lambda: self._copy_selected_id(row))
        menu.addAction(tr("Копировать данные"), lambda: self._copy_selected_data(row))
        menu.addAction(tr("Копировать всю строку"), lambda: self._copy_selected_row(row))
        menu.addAction(tr("Создать триггер"), lambda: self._create_trigger_from_row(row))
        menu.addAction(tr("Показать варианты данных"), lambda: self._show_data_variants(row))
        menu.addAction(tr("Битовая карта"), lambda: self._show_bitmap(row))
        menu.exec(self._table.viewport().mapToGlobal(position))

    def _copy_selected_id(self, row: int) -> None:
        item = self._table.item(row, 1)
        if item is not None:
            QApplication.clipboard().setText(item.text())

    def _copy_selected_data(self, row: int) -> None:
        values = []
        for col in range(2, 10):
            item = self._table.item(row, col)
            if item is not None and item.text():
                values.append(item.text())
        QApplication.clipboard().setText(" ".join(values))

    def _copy_selected_row(self, row: int) -> None:
        values = [self._table.item(row, col).text() if self._table.item(row, col) is not None else "" for col in range(self._table.columnCount())]
        QApplication.clipboard().setText("  ".join(values))

    def _create_trigger_from_row(self, row: int) -> None:
        id_item = self._table.item(row, 1)
        if id_item is None:
            return
        data_values = []
        for col in range(2, 10):
            item = self._table.item(row, col)
            data_values.append(item.text() if item is not None else "")
        self.create_trigger_requested.emit({"id": id_item.text(), "data": data_values})

    def _show_data_variants(self, row: int) -> None:
        id_item = self._table.item(row, 1)
        if id_item is None:
            return
        can_id = hex_to_int(id_item.text())
        if can_id is None:
            return
        variants = self._id_data_variants.get(can_id, set())
        if not variants:
            QMessageBox.information(self, tr("Информация"), tr("Нет вариантов данных для этого ID"))
            return
        dialog = DataVariantsDialog(can_id, variants, self)
        dialog.exec()

    def _show_bitmap(self, row: int) -> None:
        id_item = self._table.item(row, 1)
        if id_item is None:
            return
        can_id = hex_to_int(id_item.text())
        if can_id is None:
            return
        data_values = []
        for col in range(2, 10):
            item = self._table.item(row, col)
            data_values.append(item.text() if item is not None else "")
        data = bytes(parse_data_bytes(data_values))
        dialog = BitmapDialog(can_id, data, self)
        dialog.exec()

    def _export_current_table(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("Сохранить таблицу в CSV"), "", "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([self._table.horizontalHeaderItem(c).text() for c in range(self._table.columnCount())])
                for row in range(self._table.rowCount()):
                    if self._table.isRowHidden(row):
                        continue
                    writer.writerow([self._table.item(row, col).text() if self._table.item(row, col) is not None else "" for col in range(self._table.columnCount())])
            logger.info("Таблица экспортирована в %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка экспорта таблицы: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось экспортировать CSV: {0}").format(exc))

    def _export_stream_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("Сохранить поток в CSV"), "", "CSV files (*.csv)")
        if not path:
            return
        QMessageBox.information(self, tr("Информация"), tr("Потоковая запись начнётся при получении кадров."))
        # Метка для внешнего обработчика — текущий CSV-рекордер вкладки
        # (используется в CanMonitorTab._start_recording)
        self._pending_stream_csv = path

    def _export_carbus_trace(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("Сохранить трассировку"), "", "Trace files (*.trc)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(";CANalyzer\n")
                for row in range(self._table.rowCount()):
                    if self._table.isRowHidden(row):
                        continue
                    time_item = self._table.item(row, 0)
                    id_item = self._table.item(row, 1)
                    data_items = [self._table.item(row, c) for c in range(2, 10)]
                    if time_item is None or id_item is None:
                        continue
                    data = " ".join(i.text() for i in data_items if i is not None and i.text())
                    f.write(f"{time_item.text()}  {id_item.text()}  {data}\n")
            logger.info("Трассировка CarBus экспортирована в %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка экспорта трассировки: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось экспортировать трассировку: {0}").format(exc))


class CanMonitorTab(QWidget):
    """Вкладка мониторинга CAN с двумя каналами."""

    create_trigger_requested = Signal(dict)

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._recording = False
        self._csv_file: Optional[TextIO] = None
        self._csv_writer: Optional[csv.writer] = None
        self._csv_path: Optional[Path] = None
        self._dbc_manager = DBCManager()
        self._create_widgets()
        self._layout_widgets()

    def _create_widgets(self) -> None:
        self._start_all_button = QPushButton(tr("Запустить оба"))
        self._start_all_button.setFixedSize(110, 28)
        self._start_all_button.setFont(QFont("Segoe UI", 9))
        self._start_all_button.clicked.connect(self._start_all)

        self._stop_all_button = QPushButton(tr("Остановить оба"))
        self._stop_all_button.setFixedSize(110, 28)
        self._stop_all_button.setFont(QFont("Segoe UI", 9))
        self._stop_all_button.clicked.connect(self._stop_all)

        self._clear_all_button = QPushButton(tr("Очистить всё"))
        self._clear_all_button.setFixedSize(110, 28)
        self._clear_all_button.setFont(QFont("Segoe UI", 9))
        self._clear_all_button.clicked.connect(self._clear_all)

        self._dbc_button = QPushButton(tr("Загрузить DBC"))
        self._dbc_button.setFixedSize(110, 28)
        self._dbc_button.setFont(QFont("Segoe UI", 9))
        self._dbc_button.clicked.connect(self._on_load_dbc)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._monitor1 = CanChannelMonitor(1, self._serial_manager, self)
        self._monitor2 = CanChannelMonitor(2, self._serial_manager, self)
        self._monitor1.create_trigger_requested.connect(self.create_trigger_requested)
        self._monitor2.create_trigger_requested.connect(self.create_trigger_requested)
        self._splitter.addWidget(self._monitor1)
        self._splitter.addWidget(self._monitor2)
        self._splitter.setSizes([450, 450])

    def _layout_widgets(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self._start_all_button)
        buttons_layout.addWidget(self._stop_all_button)
        buttons_layout.addWidget(self._clear_all_button)
        buttons_layout.addWidget(self._dbc_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        layout.addWidget(self._splitter)

    def _start_all(self) -> None:
        self._monitor1._start()
        self._monitor2._start()
        logger.info("Запущен мониторинг обоих CAN-каналов")

    def _stop_all(self) -> None:
        self._monitor1._stop()
        self._monitor2._stop()
        logger.info("Остановлен мониторинг обоих CAN-каналов")

    def _clear_all(self) -> None:
        self._monitor1._clear()
        self._monitor2._clear()

    def process_frame(self, frame: Dict[str, object]) -> None:
        channel = int(frame["channel"])
        if channel == 1:
            self._monitor1.add_frame(frame)
        elif channel == 2:
            self._monitor2.add_frame(frame)
        self._write_frame_to_csv(frame)

    def _on_load_dbc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Загрузить DBC"), "", "DBC files (*.dbc)")
        if not path:
            return
        if self._dbc_manager.load_dbc(path):
            QMessageBox.information(self, tr("Готово"), tr("DBC загружен: {0}").format(path))
            for monitor in (self._monitor1, self._monitor2):
                monitor._apply_filters()
        else:
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось загрузить DBC"))

    def set_dbc(self, dbc) -> None:
        """Уведомляет вкладку о смене DBC."""
        for monitor in (self._monitor1, self._monitor2):
            monitor._apply_filters()

    def _start_recording(self, path: str) -> None:
        try:
            self._csv_path = Path(path)
            self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(["timestamp", "channel", "id", "dlc", "data"])
            self._recording = True
            logger.info("Потоковая запись CAN начата: %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка открытия CSV: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось открыть файл: {0}").format(exc))

    def _stop_recording(self) -> None:
        self._recording = False
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка закрытия CSV: %s", exc)
            finally:
                self._csv_file = None
                self._csv_writer = None

    def _write_frame_to_csv(self, frame: Dict[str, object]) -> None:
        if not self._recording or self._csv_writer is None:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
        frame_id = int(frame["id"])
        data = bytes(frame["data"])
        self._csv_writer.writerow([timestamp, frame["channel"], int_to_hex(frame_id, 8), len(data), bytes_to_hex_string(data)])
