"""Страница «Триггеры» с таблицей триггеров и диалогом добавления/редактирования."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.can_protocol import pack_can_frame
from core.serial_manager import SerialManager
from models.config import Config
from models.logger import get_logger
from models.translations import _ as tr
from models.utils import format_data_bytes, hex_to_int, int_to_hex, parse_data_bytes

logger = get_logger(__name__)


class TriggerEditDialog(QDialog):
    """Диалог добавления/редактирования триггера."""

    def __init__(self, trigger: Optional[Dict[str, object]] = None, parent: Optional[QWidget] = None) -> None:
        """Создаёт диалог.

        Args:
            trigger: Существующий триггер для редактирования или None.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._trigger = trigger or {}
        self.setWindowTitle(tr("Триггер") if trigger is None else tr("Редактирование триггера"))
        self.setMinimumWidth(360)
        self._create_widgets()
        self._build_layout()
        self._load_data()

    def _create_widgets(self) -> None:
        """Создаёт элементы диалога."""
        font = QFont("Segoe UI", 10)

        self._active_check = QCheckBox(tr("Активен"))
        self._active_check.setFont(font)

        self._id_edit = QLineEdit()
        self._id_edit.setFont(font)
        self._id_edit.setPlaceholderText(tr("ID HEX"))
        self._id_edit.setMaxLength(8)

        self._data_edit = QLineEdit()
        self._data_edit.setFont(font)
        self._data_edit.setPlaceholderText(tr("D0 D1 D2 ..."))

        self._resp_id_edit = QLineEdit()
        self._resp_id_edit.setFont(font)
        self._resp_id_edit.setPlaceholderText(tr("ID HEX"))
        self._resp_id_edit.setMaxLength(8)

        self._resp_data_edit = QLineEdit()
        self._resp_data_edit.setFont(font)
        self._resp_data_edit.setPlaceholderText(tr("D0 D1 D2 ..."))

        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 10000)
        self._delay_spin.setValue(0)
        self._delay_spin.setSuffix(tr(" мс"))
        self._delay_spin.setFont(font)

        self._save_button = QPushButton(tr("Сохранить"))
        self._save_button.setFixedSize(100, 30)
        self._save_button.setFont(font)
        self._save_button.clicked.connect(self.accept)

        self._cancel_button = QPushButton(tr("Отмена"))
        self._cancel_button.setFixedSize(100, 30)
        self._cancel_button.setFont(font)
        self._cancel_button.clicked.connect(self.reject)

    def _build_layout(self) -> None:
        """Собирает компоновку диалога."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self._active_check)
        layout.addWidget(QLabel(tr("ID условия:")))
        layout.addWidget(self._id_edit)
        layout.addWidget(QLabel(tr("Данные условия:")))
        layout.addWidget(self._data_edit)
        layout.addWidget(QLabel(tr("ID ответа:")))
        layout.addWidget(self._resp_id_edit)
        layout.addWidget(QLabel(tr("Данные ответа:")))
        layout.addWidget(self._resp_data_edit)
        layout.addWidget(QLabel(tr("Задержка ответа:")))
        layout.addWidget(self._delay_spin)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._cancel_button)
        buttons_layout.addWidget(self._save_button)
        layout.addLayout(buttons_layout)

    def _load_data(self) -> None:
        """Заполняет поля данными триггера."""
        self._active_check.setChecked(self._trigger.get("active", True))
        self._id_edit.setText(self._trigger.get("id", ""))
        self._data_edit.setText(self._trigger.get("data", ""))
        self._resp_id_edit.setText(self._trigger.get("resp_id", ""))
        self._resp_data_edit.setText(self._trigger.get("resp_data", ""))
        self._delay_spin.setValue(int(self._trigger.get("delay", 0)))

    def get_trigger(self) -> Optional[Dict[str, object]]:
        """Возвращает триггер из полей диалога."""
        can_id = hex_to_int(self._id_edit.text())
        if can_id is None:
            QMessageBox.warning(self, tr("Ошибка"), tr("Неверный ID условия"))
            return None
        resp_id = hex_to_int(self._resp_id_edit.text())
        if resp_id is None:
            resp_id = can_id
        return {
            "active": self._active_check.isChecked(),
            "id": self._id_edit.text().strip(),
            "data": self._data_edit.text().strip(),
            "resp_id": int_to_hex(resp_id, 8),
            "resp_data": self._resp_data_edit.text().strip(),
            "delay": self._delay_spin.value(),
        }


class CanTriggerTab(QWidget):
    """Страница управления триггерами CAN."""

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        """Создаёт страницу триггеров.

        Args:
            serial_manager: Менеджер COM-порта для отправки ответов.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._config = Config()
        self._active = False
        self._triggers: List[Dict[str, object]] = []
        self._trigger_counters: List[int] = []

        self._create_widgets()
        self._build_layout()
        self._load_config()

    def _create_widgets(self) -> None:
        """Создаёт элементы управления страницы."""
        font = QFont("Segoe UI", 10)

        self._title = QLabel(tr("Триггеры CAN"))
        self._title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title.setProperty("title", True)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([tr("№"), tr("Условие"), tr("Действие"), tr("Статус"), tr("Срабатываний")])
        self._table.setFont(font)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 220)
        self._table.setColumnWidth(2, 220)
        self._table.setColumnWidth(3, 70)
        self._table.setColumnWidth(4, 90)

        self._add_button = QPushButton(tr("Добавить"))
        self._add_button.setFixedSize(90, 28)
        self._add_button.setFont(font)
        self._add_button.clicked.connect(self._on_add)

        self._edit_button = QPushButton(tr("Редактировать"))
        self._edit_button.setFixedSize(110, 28)
        self._edit_button.setFont(font)
        self._edit_button.clicked.connect(self._on_edit)

        self._delete_button = QPushButton(tr("Удалить"))
        self._delete_button.setFixedSize(90, 28)
        self._delete_button.setFont(font)
        self._delete_button.clicked.connect(self._on_delete)

        self._apply_button = QPushButton(tr("Применить"))
        self._apply_button.setFixedSize(110, 30)
        self._apply_button.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._apply_button.clicked.connect(self._apply_triggers)

        self._stop_button = QPushButton(tr("Остановить"))
        self._stop_button.setFixedSize(110, 30)
        self._stop_button.setFont(font)
        self._stop_button.clicked.connect(self._stop_triggers)

        self._save_button = QPushButton(tr("Сохранить в файл"))
        self._save_button.setFixedSize(120, 28)
        self._save_button.setFont(font)
        self._save_button.clicked.connect(self._save_triggers_to_file)

        self._load_button = QPushButton(tr("Загрузить из файла"))
        self._load_button.setFixedSize(130, 28)
        self._load_button.setFont(font)
        self._load_button.clicked.connect(self._load_triggers_from_file)

    def _build_layout(self) -> None:
        """Собирает компоновку страницы."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._title)
        layout.addWidget(self._table)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        buttons_layout.addWidget(self._add_button)
        buttons_layout.addWidget(self._edit_button)
        buttons_layout.addWidget(self._delete_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._apply_button)
        buttons_layout.addWidget(self._stop_button)
        layout.addLayout(buttons_layout)

        file_layout = QHBoxLayout()
        file_layout.setSpacing(8)
        file_layout.addStretch()
        file_layout.addWidget(self._save_button)
        file_layout.addWidget(self._load_button)
        layout.addLayout(file_layout)

    def _load_config(self) -> None:
        """Загружает триггеры из конфигурации."""
        triggers = self._config.get("triggers", [])
        if not isinstance(triggers, list):
            triggers = []
        self._triggers = triggers
        self._trigger_counters = [0] * len(triggers)
        self._refresh_table()

    def _save_config(self) -> None:
        """Сохраняет триггеры в конфигурацию."""
        self._config.set("triggers", self._triggers)

    def _refresh_table(self) -> None:
        """Обновляет таблицу триггеров."""
        self._table.setRowCount(len(self._triggers))
        for i, trigger in enumerate(self._triggers):
            active = trigger.get("active", False)
            status = tr("Активен") if active else tr("Неактивен")
            condition = f"ID: {trigger.get('id', '-')} | {trigger.get('data', '')}"
            action = f"ID: {trigger.get('resp_id', '-')} | {trigger.get('resp_data', '')}"
            counter = self._trigger_counters[i] if i < len(self._trigger_counters) else 0

            item = QTableWidgetItem(str(i + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 0, item)
            self._table.setItem(i, 1, QTableWidgetItem(condition))
            self._table.setItem(i, 2, QTableWidgetItem(action))
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 3, status_item)
            counter_item = QTableWidgetItem(str(counter))
            counter_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 4, counter_item)

    def _on_add(self) -> None:
        """Открывает диалог добавления триггера."""
        dialog = TriggerEditDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            trigger = dialog.get_trigger()
            if trigger is not None:
                self._triggers.append(trigger)
                self._trigger_counters.append(0)
                self._save_config()
                self._refresh_table()

    def _on_edit(self) -> None:
        """Открывает диалог редактирования выбранного триггера."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._triggers):
            QMessageBox.warning(self, tr("Внимание"), tr("Выберите триггер для редактирования"))
            return
        dialog = TriggerEditDialog(self._triggers[row], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            trigger = dialog.get_trigger()
            if trigger is not None:
                self._triggers[row] = trigger
                self._save_config()
                self._refresh_table()

    def _on_delete(self) -> None:
        """Удаляет выбранный триггер."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._triggers):
            QMessageBox.warning(self, tr("Внимание"), tr("Выберите триггер для удаления"))
            return
        del self._triggers[row]
        if row < len(self._trigger_counters):
            del self._trigger_counters[row]
        self._save_config()
        self._refresh_table()

    def _build_internal_triggers(self) -> None:
        """Формирует внутренний список активных триггеров для обработки кадров."""
        self._internal_triggers = []
        for i, trigger in enumerate(self._triggers):
            if not trigger.get("active", False):
                continue
            can_id = hex_to_int(trigger.get("id", ""))
            if can_id is None:
                continue
            data = parse_data_bytes(trigger.get("data", "").split())
            resp_id = hex_to_int(trigger.get("resp_id", ""))
            if resp_id is None:
                resp_id = can_id
            resp_data = parse_data_bytes(trigger.get("resp_data", "").split())
            try:
                delay_ms = int(trigger.get("delay", 0))
            except ValueError:
                delay_ms = 0
            self._internal_triggers.append({
                "index": i,
                "id": can_id,
                "data": data,
                "resp_id": resp_id,
                "resp_data": resp_data,
                "delay": max(0, delay_ms),
            })

    def _apply_triggers(self) -> None:
        """Активирует обработку триггеров."""
        self._save_config()
        self._build_internal_triggers()
        self._active = True
        logger.info("Триггеры CAN применены: %d активных", len(self._internal_triggers))
        QMessageBox.information(self, tr("Триггеры"), tr("Триггеры применены и активны"))

    def _stop_triggers(self) -> None:
        """Останавливает обработку триггеров."""
        self._active = False
        logger.info("Обработка триггеров CAN остановлена")
        QMessageBox.information(self, tr("Триггеры"), tr("Обработка триггеров остановлена"))

    def _send_trigger_response(self, resp_frame: bytes) -> None:
        """Отправляет подготовленный ответный кадр."""
        self._serial_manager.send_data(resp_frame)

    def process_frame(self, frame: Dict[str, object]) -> None:
        """Проверяет входящий кадр на совпадение с активными триггерами."""
        if not self._active:
            return
        if not getattr(self, "_internal_triggers", []):
            return

        frame_id = int(frame["id"])
        frame_data = bytes(frame["data"])

        for trigger in self._internal_triggers:
            if trigger["id"] != frame_id:
                continue
            if trigger["data"]:
                if len(frame_data) < len(trigger["data"]):
                    continue
                if not all(frame_data[i] == trigger["data"][i] for i in range(len(trigger["data"]))):
                    continue
            idx = trigger["index"]
            self._trigger_counters[idx] += 1
            counter_item = self._table.item(idx, 4)
            if counter_item is not None:
                counter_item.setText(str(self._trigger_counters[idx]))
            resp_frame = pack_can_frame(
                int(frame["channel"]),
                trigger["resp_id"],
                bytes(trigger["resp_data"]),
            )
            delay_ms = trigger.get("delay", 0)
            if delay_ms > 0:
                QTimer.singleShot(delay_ms, lambda rf=resp_frame: self._send_trigger_response(rf))
            else:
                self._send_trigger_response(resp_frame)
            logger.info(
                "Сработал триггер: ID=0x%s -> ответ ID=0x%s в канал %s (задержка %d мс)",
                int_to_hex(frame_id, 8),
                int_to_hex(trigger["resp_id"], 8),
                frame["channel"],
                delay_ms,
            )

    def get_config(self) -> List[Dict[str, object]]:
        """Возвращает текущие настройки триггеров для экспорта."""
        self._save_config()
        return self._config.get("triggers", [])

    def set_config(self, triggers: List[Dict[str, object]]) -> None:
        """Загружает настройки триггеров из импортированного профиля."""
        self._config.set("triggers", triggers)
        self._load_config()

    def create_trigger_from_packet(self, packet: Dict[str, object]) -> None:
        """Создаёт триггер из пакета мониторинга.

        Args:
            packet: Словарь с ключами 'id' (строка HEX) и 'data' (список строк HEX).
        """
        trigger = {
            "active": True,
            "id": packet.get("id", ""),
            "data": " ".join(packet.get("data", [])),
            "resp_id": packet.get("id", ""),
            "resp_data": "",
            "delay": 0,
        }
        self._triggers.append(trigger)
        self._trigger_counters.append(0)
        self._save_config()
        self._refresh_table()

    def _save_triggers_to_file(self) -> None:
        """Сохраняет только набор триггеров в JSON-файл."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Сохранить триггеры"),
            "",
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.get_config(), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Триггеры сохранены в %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка сохранения триггеров: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось сохранить триггеры: {0}").format(exc))

    def _load_triggers_from_file(self) -> None:
        """Загружает набор триггеров из JSON-файла."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Загрузить триггеры"),
            "",
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            triggers = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(triggers, list):
                raise ValueError(tr("Файл должен содержать список триггеров"))
            self.set_config(triggers)
            logger.info("Триггеры загружены из %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка загрузки триггеров: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), tr("Не удалось загрузить триггеры: {0}").format(exc))
