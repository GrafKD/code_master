"""Главное окно приложения «Код Мастер» с мастером подключения."""

import sys
import traceback
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
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
from ui.can_monitor_tab import CanMonitorTab
from ui.can_trigger_tab import CanTriggerTab
from ui.dark_theme import apply_dark_theme, apply_light_theme
from ui.flexible_logic_tab import FlexibleLogicTab

logger = get_logger(__name__)

try:
    from serial.tools.list_ports import comports
except Exception:  # noqa: BLE001
    def comports() -> list:
        return []


class StartupWidget(QWidget):
    """Начальное окно: мастер подключения и панель настроек."""

    connected = Signal()

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        """Создаёт виджет начального окна.

        Args:
            serial_manager: Менеджер COM-порта.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._config = Config()

        self._create_widgets()
        self._build_layout()

    def _create_widgets(self) -> None:
        """Создаёт элементы начального окна."""
        font = QFont("Segoe UI", 10)

        # Приветственный вид
        self._title_label = QLabel("Код Мастер")
        self._title_label.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setProperty("title", True)

        self._subtitle_label = QLabel("Настройка подключения")
        self._subtitle_label.setFont(QFont("Segoe UI", 12))
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._port_info_label = QLabel("Порт не выбран")
        self._port_info_label.setFont(QFont("Segoe UI", 11))
        self._port_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._refresh_button = QPushButton("Обновить")
        self._refresh_button.setFixedSize(140, 40)
        self._refresh_button.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_button.clicked.connect(self._on_refresh)

        self._configure_button = QPushButton("Настроить")
        self._configure_button.setFixedSize(140, 40)
        self._configure_button.setFont(QFont("Segoe UI", 11))
        self._configure_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._configure_button.clicked.connect(self._show_settings)

        # Панель настроек
        self._settings_port_label = QLabel("COM-порт:")
        self._settings_port_label.setFont(font)
        self._settings_port_combo = QComboBox()
        self._settings_port_combo.setFont(font)

        self._settings_baud_label = QLabel("Скорость:")
        self._settings_baud_label.setFont(font)
        self._settings_baud_combo = QComboBox()
        self._settings_baud_combo.setFont(font)
        self._settings_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800"])

        self._settings_emulation_check = QCheckBox("Режим эмуляции")
        self._settings_emulation_check.setFont(font)
        self._settings_emulation_check.stateChanged.connect(self._on_emulation_changed)

        self._settings_auto_reconnect_check = QCheckBox("Автопереподключение")
        self._settings_auto_reconnect_check.setFont(font)

        self._settings_error_label = QLabel("Вероятность ошибки CAN: 0%")
        self._settings_error_label.setFont(font)
        self._settings_error_label.setEnabled(False)

        self._settings_error_slider = QSlider(Qt.Orientation.Horizontal)
        self._settings_error_slider.setRange(0, 100)
        self._settings_error_slider.setValue(0)
        self._settings_error_slider.setEnabled(False)
        self._settings_error_slider.valueChanged.connect(self._on_error_slider_changed)

        self._settings_save_button = QPushButton("Сохранить")
        self._settings_save_button.setFixedSize(130, 34)
        self._settings_save_button.setFont(font)
        self._settings_save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_save_button.clicked.connect(self._on_settings_save)

        self._settings_back_button = QPushButton("Назад")
        self._settings_back_button.setFixedSize(130, 34)
        self._settings_back_button.setFont(font)
        self._settings_back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_back_button.clicked.connect(self._show_welcome)

        self._settings_status_label = QLabel("")
        self._settings_status_label.setFont(font)
        self._settings_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _build_layout(self) -> None:
        """Собирает компоновку с внутренним стеком."""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()

        # Приветственный вид
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setSpacing(16)
        welcome_layout.setContentsMargins(40, 40, 40, 40)
        welcome_layout.addStretch(1)
        welcome_layout.addWidget(self._title_label)
        welcome_layout.addWidget(self._subtitle_label)
        welcome_layout.addSpacing(20)
        welcome_layout.addWidget(self._port_info_label)
        welcome_layout.addSpacing(30)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._refresh_button)
        buttons_layout.addWidget(self._configure_button)
        buttons_layout.addStretch()
        welcome_layout.addLayout(buttons_layout)
        welcome_layout.addStretch(2)

        # Панель настроек
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.setSpacing(12)
        settings_layout.setContentsMargins(60, 30, 60, 30)
        settings_layout.addStretch()
        settings_layout.addWidget(QLabel("Настройки подключения"))
        settings_layout.addWidget(self._settings_port_label)
        settings_layout.addWidget(self._settings_port_combo)
        settings_layout.addWidget(self._settings_baud_label)
        settings_layout.addWidget(self._settings_baud_combo)
        settings_layout.addWidget(self._settings_emulation_check)
        settings_layout.addWidget(self._settings_auto_reconnect_check)
        settings_layout.addWidget(self._settings_error_label)
        settings_layout.addWidget(self._settings_error_slider)
        settings_layout.addSpacing(10)

        settings_buttons_layout = QHBoxLayout()
        settings_buttons_layout.setSpacing(10)
        settings_buttons_layout.addStretch()
        settings_buttons_layout.addWidget(self._settings_back_button)
        settings_buttons_layout.addWidget(self._settings_save_button)
        settings_buttons_layout.addStretch()
        settings_layout.addLayout(settings_buttons_layout)
        settings_layout.addWidget(self._settings_status_label)
        settings_layout.addStretch()

        self._stack.addWidget(welcome)
        self._stack.addWidget(settings)
        layout.addWidget(self._stack)

        self._load_defaults()
        self._update_port_info()

    def _load_defaults(self) -> None:
        """Загружает сохранённые настройки и список портов."""
        self._settings_port_combo.addItem("FAKE (эмулятор)")
        for port_info in comports():
            self._settings_port_combo.addItem(port_info.device)

        saved_port = self._config.get("port", "")
        if saved_port:
            index = self._settings_port_combo.findText(saved_port)
            if index < 0:
                self._settings_port_combo.addItem(saved_port)
                index = self._settings_port_combo.count() - 1
            self._settings_port_combo.setCurrentIndex(index)

        saved_baud = str(self._config.get("baudrate", 115200))
        index = self._settings_baud_combo.findText(saved_baud)
        if index >= 0:
            self._settings_baud_combo.setCurrentIndex(index)

        self._settings_emulation_check.setChecked(self._config.get("emulation", False))
        self._settings_auto_reconnect_check.setChecked(self._config.get("auto_reconnect", False))
        error_prob = self._config.get("error_probability", 0)
        self._settings_error_slider.setValue(error_prob)
        self._settings_error_label.setText(f"Вероятность ошибки CAN: {error_prob}%")
        self._on_emulation_changed()

    def _on_emulation_changed(self, state: int = 0) -> None:
        """Включает/отключает настройку ошибок."""
        enabled = self._settings_emulation_check.isChecked()
        self._settings_error_label.setEnabled(enabled)
        self._settings_error_slider.setEnabled(enabled)

    def _on_error_slider_changed(self, value: int) -> None:
        """Обновляет текст метки вероятности ошибки."""
        self._settings_error_label.setText(f"Вероятность ошибки CAN: {value}%")

    def _update_port_info(self) -> None:
        """Обновляет информацию о текущем порте."""
        port = self._config.get("port", "")
        if not port:
            self._port_info_label.setText("Порт не выбран")
        elif self._serial_manager.is_open():
            self._port_info_label.setText(f"Порт: {port} (подключён)")
        else:
            self._port_info_label.setText(f"Порт: {port} (не подключён)")

    def _show_welcome(self) -> None:
        """Показывает приветственный вид."""
        self._settings_status_label.setText("")
        self._stack.setCurrentIndex(0)
        self._update_port_info()

    def _show_settings(self) -> None:
        """Показывает панель настроек."""
        self._settings_status_label.setText("")
        self._stack.setCurrentIndex(1)

    def _on_settings_save(self) -> None:
        """Сохраняет настройки и возвращает к приветственному виду."""
        port_text = self._settings_port_combo.currentText()
        port_name = "FAKE" if port_text.startswith("FAKE") else port_text
        baudrate = int(self._settings_baud_combo.currentText())
        emulation = self._settings_emulation_check.isChecked()
        auto_reconnect = self._settings_auto_reconnect_check.isChecked()
        error_probability = self._settings_error_slider.value() if emulation else 0

        self._config.set("port", port_name)
        self._config.set("baudrate", baudrate)
        self._config.set("emulation", emulation)
        self._config.set("auto_reconnect", auto_reconnect)
        self._config.set("error_probability", error_probability)

        if self._serial_manager.is_open():
            self._serial_manager.close_port()
        if auto_reconnect:
            self._serial_manager.open_port(port_name, baudrate, emulation, True, error_probability)

        self._settings_status_label.setText("Настройки сохранены")
        logger.info("Настройки COM-порта сохранены: %s", port_name)

        # Небольшая задержка для показа статуса
        QTimer.singleShot(500, self._show_welcome)

    def _on_refresh(self) -> None:
        """Сканирует порты и пытается автоматически подключиться."""
        # Обновляем список портов
        self._settings_port_combo.clear()
        self._settings_port_combo.addItem("FAKE (эмулятор)")
        for port_info in comports():
            self._settings_port_combo.addItem(port_info.device)

        saved_port = self._config.get("port", "")
        baudrate = self._config.get("baudrate", 115200)
        emulation = self._config.get("emulation", False)
        auto_reconnect = self._config.get("auto_reconnect", False)
        error_probability = self._config.get("error_probability", 0)

        port_to_try = saved_port if saved_port else None
        if not port_to_try:
            # Берём первый реальный порт
            for i in range(self._settings_port_combo.count()):
                text = self._settings_port_combo.itemText(i)
                if not text.startswith("FAKE"):
                    port_to_try = text
                    break
            if not port_to_try:
                port_to_try = "FAKE"
                emulation = True

        logger.info("Автоподключение к порту %s", port_to_try)
        if self._serial_manager.open_port(port_to_try, baudrate, emulation, auto_reconnect, error_probability):
            self._config.set("port", port_to_try)
            self._update_port_info()
            self.connected.emit()
        else:
            self._config.set("port", port_to_try)
            self._update_port_info()
            QMessageBox.warning(
                self,
                "Подключение",
                f"Не удалось подключиться к {port_to_try}.\nНажмите «Настроить» для ручного выбора.",
            )


class MainWindow(QMainWindow):
    """Главное окно приложения «Код Мастер»."""

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
        self._set_theme_button_icon()
        self._set_lang_button_text()

        # Показываем мастер подключения, если порт не подключён
        if not self._serial_manager.is_open():
            self._mode_stack.setCurrentIndex(0)
        else:
            self._mode_stack.setCurrentIndex(1)
            self._update_port_indicator()

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

        # Меню-карточки (3 вкладки)
        self._menu_group = QButtonGroup(self)
        self._menu_group.setExclusive(True)

        self._menu_buttons = []
        menu_items = [
            ("⚡", tr("Триггеры")),
            ("🔍", tr("Мониторинг")),
            ("🧩", tr("Гибкая логика")),
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

        # Начальное окно
        self._startup_widget = StartupWidget(self._serial_manager, self)

        # Основной режим
        self._main_widget = QWidget()
        self._main_stack = QStackedWidget()
        self._trigger_tab = CanTriggerTab(self._serial_manager, self)
        self._monitor_tab = CanMonitorTab(self._serial_manager, self)
        self._flexible_logic_tab = FlexibleLogicTab(self)

        self._main_stack.addWidget(self._trigger_tab)       # 0 Триггеры
        self._main_stack.addWidget(self._monitor_tab)        # 1 Мониторинг
        self._main_stack.addWidget(self._flexible_logic_tab)  # 2 Гибкая логика

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

        # Панель меню-карточек (только для основного режима)
        menu_panel = QWidget()
        menu_panel.setObjectName("menuPanel")
        menu_panel.setFixedHeight(80)
        menu_layout = QHBoxLayout(menu_panel)
        menu_layout.setContentsMargins(12, 12, 12, 8)
        menu_layout.setSpacing(8)
        for btn in self._menu_buttons:
            menu_layout.addWidget(btn)
        menu_layout.addStretch()

        # Собираем основной режим
        main_layout = QVBoxLayout(self._main_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(menu_panel)
        main_layout.addWidget(self._main_stack, 1)
        main_layout.addWidget(self._status_bar)

        # Глобальный стек: начальное окно / основной режим
        self._mode_stack = QStackedWidget()
        self._mode_stack.addWidget(self._startup_widget)
        self._mode_stack.addWidget(self._main_widget)

        root.addWidget(self._mode_stack, 1)

    def _connect_signals(self) -> None:
        """Подключает сигналы."""
        self._menu_group.idClicked.connect(self._set_page)
        self._startup_widget.connected.connect(self._on_startup_connected)
        self._serial_manager.connection_changed.connect(self._update_port_indicator)
        self._serial_manager.error_occurred.connect(self._on_serial_error)
        self._serial_manager.heartbeat.connect(self._on_heartbeat)
        self._serial_manager.new_can_frame.connect(self._monitor_tab.process_frame)
        self._serial_manager.new_can_frame.connect(self._trigger_tab.process_frame)
        self._monitor_tab.create_trigger_requested.connect(self._on_create_trigger_from_packet)

    def _setup_shortcuts(self) -> None:
        """Настраивает горячие клавиши."""
        QShortcut(QKeySequence("Ctrl+M"), self, activated=lambda: self._set_page(1))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self._set_page(0))
        QShortcut(QKeySequence("Esc"), self, activated=self._handle_esc)

    def _on_startup_connected(self) -> None:
        """Переключает в основной режим после успешного подключения."""
        self._mode_stack.setCurrentIndex(1)
        self._update_port_indicator()
        self._status_label.setText(tr("Готов"))
        logger.info("Переключение в рабочий режим")

    def _set_page(self, index: int) -> None:
        """Переключает центральную страницу основного режима."""
        if 0 <= index < self._main_stack.count():
            self._main_stack.setCurrentIndex(index)
            self._menu_buttons[index].setChecked(True)

    def _open_settings(self) -> None:
        """Открывает панель настроек внутри главного окна."""
        self._mode_stack.setCurrentIndex(0)
        self._startup_widget._show_settings()

    def _handle_esc(self) -> None:
        """Сбрасывает фокус."""
        self.setFocus()

    def _on_create_trigger_from_packet(self, packet: dict) -> None:
        """Переключает на страницу триггеров и заполняет первый свободный."""
        self._trigger_tab.create_trigger_from_packet(packet)
        self._set_page(0)

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
