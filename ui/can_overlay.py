"""Плавающий индикатор активности CAN-подключения поверх всех окон."""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QWidget


class CanOverlay(QWidget):
    """Маленькое окно-индикатор активности CAN, всегда поверх других окон."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Создаёт индикатор."""
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(100, 40)
        self.setWindowTitle("CAN")

        self._indicator = QLabel(self)
        self._indicator.setGeometry(4, 4, 92, 32)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._indicator.setText("CAN")
        self._indicator.setStyleSheet("background-color: #666666; color: #FFFFFF; border-radius: 4px;")
        self._indicator.setToolTip("Индикатор активности CAN")

        self._inactive_timer = QTimer(self)
        self._inactive_timer.timeout.connect(self._set_no_activity)
        self._inactive_timer.setSingleShot(True)

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._reset_color)
        self._blink_timer.setSingleShot(True)

        self._drag_pos = None
        self._set_default_color()

    def _set_default_color(self) -> None:
        """Устанавливает серый цвет индикатора."""
        self._indicator.setStyleSheet("background-color: #666666; color: #FFFFFF; border-radius: 4px;")

    def _set_active_color(self) -> None:
        """Подсвечивает индикатор зелёным на 200 мс."""
        self._indicator.setStyleSheet("background-color: #6C8CFF; color: #FFFFFF; border-radius: 4px;")
        self._blink_timer.start(200)
        self._inactive_timer.start(3000)

    def _reset_color(self) -> None:
        """Возвращает индикатор к серому после мигания."""
        self._set_default_color()

    def _set_no_activity(self) -> None:
        """Переключает индикатор в красный при отсутствии активности."""
        self._indicator.setStyleSheet("background-color: #F44336; color: #FFFFFF; border-radius: 4px;")

    def pulse(self) -> None:
        """Вызывает мигание индикатора (например, при получении кадра)."""
        self._set_active_color()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Запоминает позицию для перетаскивания."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Перетаскивает окно за левую кнопку мыши."""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
