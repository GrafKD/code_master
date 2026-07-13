"""Трэйс CAN-шины: две хронологические таблицы для CAN1 и CAN2."""

import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.dbc_manager import DBCManager
from core.serial_manager import SerialManager
from models.logger import get_logger
from models.translations import _ as tr
from models.utils import format_data_bytes, hex_to_int, int_to_hex, parse_packet_string

logger = get_logger(__name__)


def _ascii_from_data(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


class CanAnalyzer(QWidget):
    """Виджет трэйса CAN-шины с двумя таблицами."""

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._dbc_manager = DBCManager()
        self._analyzing = False
        self._start_time = 0.0
        self._id_last_time: Dict[int, float] = {}
        self._create_widgets()
        self._build_layout()

    def retranslate_ui(self) -> None:
        self._start_button.setText(tr("Начать анализ"))
        self._stop_button.setText(tr("Завершить анализ"))
        self._title.setText(tr("Трэйс CAN-шины"))
        for table in (self._table1, self._table2):
            table.setHorizontalHeaderLabels(
                [tr("Время"), tr("ID"), tr("DLC"), tr("DATA"), tr("Период"), tr("ASCII"), tr("Пояснение")]
            )

    def set_dbc(self, dbc_manager) -> None:
        self._dbc_manager = dbc_manager

    def _create_widgets(self) -> None:
        font = QFont("Segoe UI", 10)
        self._title = QLabel(tr("Трэйс CAN-шины"))
        self._title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title.setProperty("title", True)

        self._start_button = QPushButton(tr("Начать анализ"))
        self._start_button.setFont(font)
        self._start_button.setMinimumHeight(32)
        self._start_button.clicked.connect(self._start_analysis)

        self._stop_button = QPushButton(tr("Завершить анализ"))
        self._stop_button.setFont(font)
        self._stop_button.setMinimumHeight(32)
        self._stop_button.clicked.connect(self._stop_analysis)

        self._table1 = self._build_table(font)
        self._table2 = self._build_table(font)

    def _build_table(self, font: QFont) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            [tr("Время"), tr("ID"), tr("DLC"), tr("DATA"), tr("Период"), tr("ASCII"), tr("Пояснение")]
        )
        table.setFont(font)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 50)
        table.setColumnWidth(3, 220)
        table.setColumnWidth(4, 90)
        table.setColumnWidth(5, 90)
        table.setColumnWidth(6, 150)
        return table

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._title)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        top_layout.addWidget(self._start_button)
        top_layout.addWidget(self._stop_button)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._table1)
        splitter.addWidget(self._table2)
        splitter.setSizes([450, 450])
        layout.addWidget(splitter, 1)

    def _start_analysis(self) -> None:
        if not self._analyzing:
            self._start_time = time.time()
            self._id_last_time.clear()
        self._analyzing = True
        self._start_button.setEnabled(False)
        self._stop_button.setEnabled(True)
        logger.info("Трэйс запущен")

    def _stop_analysis(self) -> None:
        self._analyzing = False
        self._start_button.setEnabled(True)
        self._stop_button.setEnabled(False)
        logger.info("Трэйс остановлен")

    def process_frame(self, frame: Dict[str, Any]) -> None:
        if not self._analyzing:
            return
        channel = int(frame.get("channel", 0))
        table = self._table1 if channel == 1 else self._table2
        self._add_trace_row(table, frame)

    def _add_trace_row(self, table: QTableWidget, frame: Dict[str, Any]) -> None:
        can_id = int(frame.get("id", 0))
        data = bytes(frame.get("data", b""))
        now = time.time()
        elapsed = now - self._start_time
        elapsed_text = f"{elapsed:.3f}"
        last_time = self._id_last_time.get(can_id)
        period_text = f"{int((now - last_time) * 1000)} ms" if last_time else ""
        self._id_last_time[can_id] = now

        id_width = 8 if can_id > 0x7FF else 3
        id_text = int_to_hex(can_id, id_width)
        dlc_text = str(len(data))
        data_text = " ".join(format_data_bytes(data))
        ascii_text = _ascii_from_data(data.ljust(8, b"\x00"))
        explanation = ""
        if self._dbc_manager.is_loaded():
            explanation = self._dbc_manager.describe_frame(can_id, data)

        row = table.rowCount()
        table.insertRow(row)
        values = [elapsed_text, id_text, dlc_text, data_text, period_text, ascii_text, explanation]
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, col, item)
        table.scrollToBottom()

    def _show_context_menu(self, position) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        row = table.currentRow()
        if row < 0:
            return
        menu = QMenu(self)
        menu.addAction(tr("Копировать пакет"), lambda: self._copy_packet(table, row))
        menu.exec(table.viewport().mapToGlobal(position))

    def _copy_packet(self, table: QTableWidget, row: int) -> None:
        id_item = table.item(row, 1)
        dlc_item = table.item(row, 2)
        data_item = table.item(row, 3)
        if id_item is None or dlc_item is None or data_item is None:
            return
        text = f"ID={id_item.text()} DLC={dlc_item.text()} DATA={data_item.text()}"
        QApplication.clipboard().setText(text)

    @staticmethod
    def parse_packet_string(text: str) -> Optional[Dict[str, Any]]:
        return parse_packet_string(text)
