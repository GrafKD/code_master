"""Главное окно приложения «Код Мастер» в стиле StarLine Master."""

import sys
import traceback
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.serial_manager import SerialManager
from core.update_checker import check_for_updates
from models.config import Config
from models.logger import get_logger, open_log_folder
from models.translations import _ as tr, set_language
from ui.can_gateway_tab import CanGatewayTab
from ui.can_monitor_tab import CanMonitorTab
from ui.can_trigger_tab import CanTriggerTab
from ui.com_settings_dialog import ComSettingsDialog
from ui.dark_theme import apply_dark_theme, apply_light_theme
from ui.firmware_tab import FirmwareTab
from ui.library_tab import LibraryTab

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Главное окно приложения с горизонтальным меню-карточками."""

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        """Создаёт главное окно.

        Args:
            serial_manager: Общий менеджер COM-порта.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._config = Config()
        set_language(self._config.get("language", "ru"))

        self.setWindowTitle(tr("Код Мастер"))
        self.resize(800, 600)
        self.setMinimumSize(640, 480)
        self.setWindowFlags(
            Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        central = QWidget(self)
        self.setCentralWidget(central)

        self._create_widgets()
        self._build_layout()
        self._connect_signals()
        self._setup_shortcuts()
        self._update_port_indicator()
        self._set_theme_button_icon()
        self._set_lang_button_text()

        saved_port = self._config.get("port", "")
        if saved_port:
            self._serial_manager.open_port(
                saved_port,
                self._config.get("baudrate", 115200),
                self._config.get("emulation", False),
                self._config.get("auto_reconnect", False),
                self._config.get("error_probability", 0),
            )

    def _create_widgets(self) -> None:
        """Создаёт виджеты главного окна."""
        font = QFont("Segoe UI", 10)

        # Верхняя панель
        self._logo_label = QLabel("🛠️ " + tr("Код Мастер"))
        self._logo_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._logo_label.setProperty("title", True)

        self._port_indicator = QLabel("●")
        self._port_indicator.setFixedSize(20, 20)
        self._port_indicator.setStyleSheet("color: #666666; font-size: 14px; background: transparent;")
        self._port_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._port_indicator.setToolTip(tr("Индикатор подключения COM-порта"))

        self._port_label = QLabel(tr("Нет подключения"))
        self._port_label.setFont(font)

        self._settings_button = QPushButton("⚙️ " + tr("Настройки"))
        self._settings_button.setFixedSize(110, 28)
        self._settings_button.setFont(font)
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.clicked.connect(self._open_settings)

        self._logs_button = QPushButton("📄 " + tr("Логи"))
        self._logs_button.setFixedSize(80, 28)
        self._logs_button.setFont(font)
        self._logs_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logs_button.clicked.connect(self._open_logs)

        self._theme_button = QPushButton("☀")
        self._theme_button.setFixedSize(36, 28)
        self._theme_button.setFont(font)
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.setToolTip(tr("Переключить светлую/тёмную тему"))
        self._theme_button.clicked.connect(self._on_theme_clicked)

        self._lang_button = QPushButton("EN")
        self._lang_button.setFixedSize(40, 28)
        self._lang_button.setFont(font)
        self._lang_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_button.setToolTip(tr("Переключить язык"))
        self._lang_button.clicked.connect(self._on_language_clicked)

        self._update_check_button = QPushButton("🔄")
        self._update_check_button.setFixedSize(36, 28)
        self._update_check_button.setFont(font)
        self._update_check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_check_button.setToolTip(tr("Проверка обновлений"))
        self._update_check_button.clicked.connect(self._on_check_updates_clicked)

        self._exit_button = QPushButton("✕ " + tr("Выход"))
        self._exit_button.setFixedSize(90, 28)
        self._exit_button.setFont(font)
        self._exit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exit_button.clicked.connect(self.close)

        # Меню-карточки
        self._menu_group = QButtonGroup(self)
        self._menu_group.setExclusive(True)

        self._menu_buttons = []
        menu_items = [
            ("🔍", tr("Поиск")),
            ("⚡", tr("Триггеры")),
            ("🚦", tr("Шлюз")),
            ("📚", tr("Библиотека")),
            ("⚙️", tr("Прошивка")),
        ]
        for icon, text in menu_items:
            btn = QPushButton(f"{icon}\n{text}")
            btn.setObjectName("menuButton")
            btn.setCheckable(True)
            btn.setFixedSize(100, 60)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._menu_buttons.append(btn)
            self._menu_group.addButton(btn)

        self._menu_buttons[0].setChecked(True)

        # Центральная область
        self._stack = QStackedWidget()
        self._monitor_tab = CanMonitorTab(self._serial_manager, self)
        self._trigger_tab = CanTriggerTab(self._serial_manager, self)
        self._gateway_tab = CanGatewayTab(self._serial_manager, self)
        self._library_tab = LibraryTab(self)
        self._firmware_tab = FirmwareTab(self._serial_manager, self)

        self._stack.addWidget(self._monitor_tab)   # 0 Поиск
        self._stack.addWidget(self._trigger_tab)   # 1 Триггеры
        self._stack.addWidget(self._gateway_tab)   # 2 Шлюз
        self._stack.addWidget(self._library_tab)   # 3 Библиотека
        self._stack.addWidget(self._firmware_tab)  # 4 Прошивка

        # Статус-бар
        self._status_bar = QStatusBar()
        self._status_label = QLabel(tr("Готов"))
        self._status_label.setFont(font)
        self._status_bar.addWidget(self._status_label)
        self._status_bar.showMessage("v1.0.0")

        # Таймер heartbeat
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._reset_port_indicator)
        self._heartbeat_timer.start(1500)

    def _build_layout(self) -> None:
        """Собирает компоновку главного окна."""
        root = QVBoxLayout(self.centralWidget())
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Верхняя панель
        top_panel = QWidget()
        top_panel.setObjectName("topPanel")
        top_panel.setFixedHeight(48)
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setSpacing(10)

        top_layout.addWidget(self._logo_label)
        top_layout.addStretch()
        top_layout.addWidget(self._port_indicator)
        top_layout.addWidget(self._port_label)
        top_layout.addSpacing(10)
        top_layout.addWidget(self._settings_button)
        top_layout.addWidget(self._logs_button)
        top_layout.addWidget(self._theme_button)
        top_layout.addWidget(self._lang_button)
        top_layout.addWidget(self._update_check_button)
        top_layout.addWidget(self._exit_button)

        root.addWidget(top_panel)

        # Панель меню-карточек
        menu_panel = QWidget()
        menu_panel.setObjectName("menuPanel")
        menu_panel.setFixedHeight(80)
        menu_layout = QHBoxLayout(menu_panel)
        menu_layout.setContentsMargins(12, 12, 12, 8)
        menu_layout.setSpacing(8)
        for btn in self._menu_buttons:
            menu_layout.addWidget(btn)
        menu_layout.addStretch()

        root.addWidget(menu_panel)

        # Центральная область
        self._stack.setSizePolicy(
            self._stack.sizePolicy().verticalPolicy(),
            self._stack.sizePolicy().horizontalPolicy(),
        )
        root.addWidget(self._stack, 1)

        # Статус-бар
        root.addWidget(self._status_bar)

    def _connect_signals(self) -> None:
        """Подключает сигналы."""
        self._menu_group.idClicked.connect(self._set_page)
        self._serial_manager.connection_changed.connect(self._update_port_indicator)
        self._serial_manager.error_occurred.connect(self._on_serial_error)
        self._serial_manager.heartbeat.connect(self._on_heartbeat)
        self._serial_manager.new_can_frame.connect(self._monitor_tab.process_frame)
        self._serial_manager.new_can_frame.connect(self._trigger_tab.process_frame)
        self._serial_manager.new_can_frame.connect(self._gateway_tab.process_frame)
        self._monitor_tab.create_trigger_requested.connect(self._on_create_trigger_from_packet)

    def _setup_shortcuts(self) -> None:
        """Настраивает горячие клавиши."""
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._open_firmware_page)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=lambda: self._set_page(0))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self._set_page(1))
        QShortcut(QKeySequence("Esc"), self, activated=self._handle_esc)

    def _set_page(self, index: int) -> None:
        """Переключает центральную страницу."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
            self._menu_buttons[index].setChecked(True)

    def _open_firmware_page(self) -> None:
        """Переходит на страницу прошивки (Ctrl+O)."""
        self._set_page(4)

    def _handle_esc(self) -> None:
        """Сбрасывает фокус."""
        self.setFocus()

    def _on_create_trigger_from_packet(self, packet: dict) -> None:
        """Переключает на страницу триггеров и заполняет первый свободный."""
        self._trigger_tab.create_trigger_from_packet(packet)
        self._set_page(1)

    def _open_settings(self) -> None:
        """Открывает модальное окно выбора COM-порта."""
        dialog = ComSettingsDialog(self._serial_manager, self)
        dialog.exec()
        self._update_port_indicator()

    def _open_logs(self) -> None:
        """Открывает папку с логами."""
        try:
            open_log_folder()
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось открыть папку с логами: %s", exc)
            QMessageBox.critical(self, tr("Ошибка"), f"Не удалось открыть папку с логами: {exc}")

    def _on_theme_clicked(self) -> None:
        """Переключает светлую/тёмную тему."""
        app = QApplication.instance()
        if app is None:
            return
        light = not self._config.get("light_theme", False)
        self._config.set("light_theme", light)
        if light:
            apply_light_theme(app)
            self._theme_button.setText("☾")
        else:
            apply_dark_theme(app)
            self._theme_button.setText("☀")
        logger.info("Переключена тема: %s", "светлая" if light else "тёмная")

    def _on_language_clicked(self) -> None:
        """Переключает язык."""
        lang = "en" if self._config.get("language", "ru") == "ru" else "ru"
        self._config.set("language", lang)
        set_language(lang)
        self._set_lang_button_text()
        QMessageBox.information(
            self,
            tr("Переключить язык"),
            "Перезапустите приложение, чтобы применить новый язык." if lang == "ru" else "Restart the application to apply the new language.",
        )
        logger.info("Переключён язык: %s", lang)

    def _set_lang_button_text(self) -> None:
        """Обновляет текст кнопки языка."""
        self._lang_button.setText("RU" if self._config.get("language", "ru") == "en" else "EN")

    def _set_theme_button_icon(self) -> None:
        """Обновляет иконку кнопки темы."""
        self._theme_button.setText("☾" if self._config.get("light_theme", False) else "☀")

    def _on_check_updates_clicked(self) -> None:
        """Проверяет обновления."""
        self._status_label.setText(tr("Проверка обновлений"))
        available, message = check_for_updates()
        self._status_label.setText(tr("Готов"))
        if available:
            QMessageBox.information(self, tr("Доступно обновление"), message)
        else:
            QMessageBox.information(self, tr("Последняя версия"), message)

    def _on_heartbeat(self) -> None:
        """Индикатор порта становится зелёным при активности."""
        self._port_indicator.setStyleSheet("color: #4CAF50; font-size: 14px; background: transparent;")

    def _reset_port_indicator(self) -> None:
        """Сбрасывает индикатор порта в базовое состояние."""
        self._update_port_indicator()

    def _update_port_indicator(self) -> None:
        """Обновляет индикатор и текст порта."""
        base_style = "font-size: 14px; background: transparent;"
        if self._serial_manager.is_open():
            self._port_indicator.setStyleSheet(f"color: #4CAF50; {base_style}")
            self._port_label.setText(self._serial_manager.current_port_name())
        elif self._config.get("port"):
            self._port_indicator.setStyleSheet(f"color: #F44336; {base_style}")
            self._port_label.setText(tr("Порт не открыт"))
        else:
            self._port_indicator.setStyleSheet(f"color: #666666; {base_style}")
            self._port_label.setText(tr("Нет подключения"))

    def _on_serial_error(self, message: str) -> None:
        """Показывает ошибку COM-порта."""
        logger.error("Ошибка COM-порта: %s", message)
        self._status_label.setText(tr("Ошибка порта"))

    def closeEvent(self, event) -> None:  # noqa: N802
        """Корректно закрывает приложение."""
        logger.info("Закрытие главного окна")
        self._firmware_tab.stop_workers()
        self._heartbeat_timer.stop()
        self._serial_manager.close_port()
        event.accept()


def show_exception_box(exc_type, exc_value, exc_tb) -> None:
    """Показывает QMessageBox при необработанном исключении."""
    message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("Необработанное исключение: %s", message)
    try:
        QMessageBox.critical(None, "Критическая ошибка", f"Произошла непредвиденная ошибка:\n{exc_value}")
    except Exception:  # noqa: BLE001
        pass


sys.excepthook = show_exception_box
