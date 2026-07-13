"""Поле ввода ID с автоматическим парсингом вставленного пакета."""

from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from models.utils import parse_packet_string


class IdPasteEdit(QLineEdit):
    """QLineEdit для ID, который при вставке пакета заполняет связанные поля."""

    def __init__(
        self,
        fill_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._fill_callback = fill_callback

    def set_fill_callback(self, fill_callback: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        self._fill_callback = fill_callback

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() == Qt.Key.Key_V
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and self._fill_callback is not None
        ):
            text = QApplication.clipboard().text()
            parsed = parse_packet_string(text)
            if parsed is not None:
                self._fill_callback(parsed)
                return
        super().keyPressEvent(event)
