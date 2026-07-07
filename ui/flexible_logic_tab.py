"""Страница «Гибкая логика» (заглушка для будущих правил и скриптов)."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FlexibleLogicTab(QWidget):
    """Страница гибкой логики с таблицей правил/скриптов."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Создаёт страницу гибкой логики.

        Args:
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._create_widgets()
        self._build_layout()

    def _create_widgets(self) -> None:
        """Создаёт элементы управления страницы."""
        self._title = QLabel("Гибкая логика")
        self._title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title.setProperty("title", True)

        self._subtitle = QLabel("Таблица правил/скриптов (заглушка)")
        self._subtitle.setFont(QFont("Segoe UI", 11))

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["№", "Условие", "Действие", "Статус"])
        self._table.setFont(QFont("Segoe UI", 10))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for i in range(1, 4):
            item = QTableWidgetItem(str(i))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i - 1, 0, item)
            self._table.setItem(i - 1, 1, QTableWidgetItem("-"))
            self._table.setItem(i - 1, 2, QTableWidgetItem("-"))
            self._table.setItem(i - 1, 3, QTableWidgetItem("Неактивен"))

        self._add_button = QPushButton("Добавить")
        self._add_button.setFixedSize(90, 28)
        self._add_button.clicked.connect(self._on_add)
        self._edit_button = QPushButton("Редактировать")
        self._edit_button.setFixedSize(110, 28)
        self._edit_button.clicked.connect(self._on_edit)
        self._delete_button = QPushButton("Удалить")
        self._delete_button.setFixedSize(90, 28)
        self._delete_button.clicked.connect(self._on_delete)

    def _build_layout(self) -> None:
        """Собирает компоновку страницы."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._table)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        buttons_layout.addWidget(self._add_button)
        buttons_layout.addWidget(self._edit_button)
        buttons_layout.addWidget(self._delete_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

    def _on_add(self) -> None:
        """Заглушка добавления правила."""
        pass

    def _on_edit(self) -> None:
        """Заглушка редактирования правила."""
        pass

    def _on_delete(self) -> None:
        """Заглушка удаления правила."""
        pass
