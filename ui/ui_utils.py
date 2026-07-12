"""Вспомогательные функции для настройки UI-элементов."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPushButton, QSizePolicy


def setup_button(button: QPushButton, bold: bool = False, height: int = 28) -> None:
    """Устанавливает политику размера кнопки по содержимому.

    Args:
        button: Кнопка, которую нужно настроить.
        bold: Использовать ли полужирный шрифт.
        height: Минимальная высота кнопки.
    """
    button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
    button.setMinimumHeight(height)
    if bold:
        button.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    button.adjustSize()
