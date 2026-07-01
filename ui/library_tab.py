"""Страница «Библиотека» (заглушка для будущих конфигураций)."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class LibraryTab(QWidget):
    """Заглушка страницы библиотеки конфигураций."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Создаёт страницу библиотеки.

        Args:
            parent: Родительский виджет.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("Библиотека конфигураций")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setProperty("title", True)

        subtitle = QLabel("Будет добавлена позже")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
