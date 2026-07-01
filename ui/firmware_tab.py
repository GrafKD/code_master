"""Страница «Прошивка» для загрузки .bin/.hex в STM32 через UART bootloader."""

from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.bootloader import Bootloader, BootloaderError
from core.serial_manager import SerialManager
from models.logger import get_logger

logger = get_logger(__name__)


class FirmwareWorker(QThread):
    """Фоновый поток для прошивки STM32 через bootloader."""

    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, serial_manager: SerialManager, file_path: str, parent: Optional[QWidget] = None) -> None:
        """Создаёт рабочий поток прошивки.

        Args:
            serial_manager: Менеджер COM-порта с открытым портом.
            file_path: Путь к файлу .bin прошивки.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._file_path = file_path

    def run(self) -> None:
        """Выполняет прошивку STM32 в фоне."""
        try:
            port = self._serial_manager._port
            if port is None:
                raise BootloaderError("COM-порт не открыт")
            import serial
            if not isinstance(port, serial.Serial):
                raise BootloaderError("Прошивка требует реальный COM-порт")
            bootloader = Bootloader(port, progress_callback=self.progress.emit)
            bootloader.flash_firmware(self._file_path)
            self.finished.emit(True, "Прошивка завершена успешно")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка прошивки")
            self.finished.emit(False, f"Ошибка прошивки: {exc}")


class DiagnosticsWorker(QThread):
    """Фоновый поток для диагностики bootloader STM32."""

    finished = Signal(bool, str)

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        """Создаёт рабочий поток диагностики.

        Args:
            serial_manager: Менеджер COM-порта с открытым портом.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager

    def run(self) -> None:
        """Выполняет диагностику bootloader в фоне."""
        try:
            port = self._serial_manager._port
            if port is None:
                raise BootloaderError("COM-порт не открыт")
            import serial
            if not isinstance(port, serial.Serial):
                raise BootloaderError("Диагностика требует реальный COM-порт")
            bootloader = Bootloader(port)
            info = bootloader.diagnostics()
            message = (
                f"Версия бутлоадера: 0x{info['version']:02X}\n"
                f"ID устройства: 0x{info['device_id']:03X}"
            )
            self.finished.emit(True, message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка диагностики bootloader")
            self.finished.emit(False, f"Ошибка диагностики: {exc}")


class FirmwareTab(QWidget):
    """Страница прошивки STM32."""

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        """Создаёт страницу прошивки.

        Args:
            serial_manager: Общий менеджер COM-порта.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._firmware_worker: Optional[FirmwareWorker] = None
        self._diagnostics_worker: Optional[DiagnosticsWorker] = None

        self._create_widgets()
        self._build_layout()

    def _create_widgets(self) -> None:
        """Создаёт элементы управления страницы."""
        self._title = QLabel("Прошивка STM32")
        self._title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title.setProperty("title", True)

        self._path_edit = QLineEdit()
        self._path_edit.setFont(QFont("Segoe UI", 10))
        self._path_edit.setPlaceholderText("Путь к файлу .bin или .hex")

        self._browse_button = QPushButton("Обзор")
        self._browse_button.setFixedSize(90, 28)
        self._browse_button.setFont(QFont("Segoe UI", 10))
        self._browse_button.clicked.connect(self._browse_file)

        self._info_button = QPushButton("Инфо")
        self._info_button.setFixedSize(90, 28)
        self._info_button.setFont(QFont("Segoe UI", 10))
        self._info_button.setToolTip("Получить версию bootloader и ID устройства")
        self._info_button.clicked.connect(self._run_diagnostics)

        self._flash_button = QPushButton("Загрузить")
        self._flash_button.setFixedSize(120, 34)
        self._flash_button.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._flash_button.clicked.connect(self._start_flash)

        self._verify_button = QPushButton("Проверить")
        self._verify_button.setFixedSize(120, 34)
        self._verify_button.setFont(QFont("Segoe UI", 10))
        self._verify_button.setToolTip("Верификация прошивки (заглушка)")
        self._verify_button.clicked.connect(self._verify_flash)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setVisible(False)

        self._log_edit = QTextEdit()
        self._log_edit.setFont(QFont("Consolas", 9))
        self._log_edit.setReadOnly(True)
        self._log_edit.setPlaceholderText("Лог прошивки...")

    def _build_layout(self) -> None:
        """Собирает компоновку страницы."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._title)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        file_row.addWidget(self._path_edit)
        file_row.addWidget(self._browse_button)
        file_row.addWidget(self._info_button)
        layout.addLayout(file_row)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        buttons_row.addWidget(self._flash_button)
        buttons_row.addWidget(self._verify_button)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        layout.addWidget(self._progress_bar)
        layout.addWidget(self._log_edit)

    def _browse_file(self) -> None:
        """Открывает диалог выбора файла прошивки."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл прошивки",
            "",
            "Firmware (*.bin *.hex);;All files (*)",
        )
        if file_path:
            self._path_edit.setText(file_path)
            self._log("Выбран файл: " + file_path)

    def _log(self, message: str) -> None:
        """Добавляет строку в лог страницы."""
        self._log_edit.append(message)
        logger.info(message)

    def _start_flash(self) -> None:
        """Запускает прошивку STM32 в фоновом потоке."""
        file_path = self._path_edit.text().strip()
        if not file_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала выберите файл прошивки")
            return
        if not self._serial_manager.is_open():
            QMessageBox.warning(self, "Предупреждение", "COM-порт не подключён")
            return

        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._flash_button.setEnabled(False)
        self._verify_button.setEnabled(False)
        self._log("Запуск прошивки...")

        self._firmware_worker = FirmwareWorker(self._serial_manager, file_path, self)
        self._firmware_worker.progress.connect(self._progress_bar.setValue)
        self._firmware_worker.finished.connect(self._on_flash_finished)
        self._firmware_worker.start()

    def _on_flash_finished(self, success: bool, message: str) -> None:
        """Обрабатывает завершение прошивки."""
        self._flash_button.setEnabled(True)
        self._verify_button.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._log(message)
        if success:
            QMessageBox.information(self, "Прошивка", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)
        self._firmware_worker = None

    def _verify_flash(self) -> None:
        """Заглушка верификации прошивки."""
        self._log("Верификация пока не реализована")
        QMessageBox.information(self, "Проверка", "Верификация пока не реализована")

    def _run_diagnostics(self) -> None:
        """Запускает диагностику bootloader."""
        if not self._serial_manager.is_open():
            QMessageBox.warning(self, "Предупреждение", "COM-порт не подключён")
            return
        self._info_button.setEnabled(False)
        self._log("Запрос информации о bootloader...")
        self._diagnostics_worker = DiagnosticsWorker(self._serial_manager, self)
        self._diagnostics_worker.finished.connect(self._on_diagnostics_finished)
        self._diagnostics_worker.start()

    def _on_diagnostics_finished(self, success: bool, message: str) -> None:
        """Обрабатывает результат диагностики."""
        self._info_button.setEnabled(True)
        self._log(message)
        if success:
            QMessageBox.information(self, "Информация", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)
        self._diagnostics_worker = None

    def stop_workers(self) -> None:
        """Останавливает фоновые потоки при закрытии приложения."""
        if self._firmware_worker is not None and self._firmware_worker.isRunning():
            self._firmware_worker.requestInterruption()
            self._firmware_worker.wait(3000)
        if self._diagnostics_worker is not None and self._diagnostics_worker.isRunning():
            self._diagnostics_worker.requestInterruption()
            self._diagnostics_worker.wait(3000)
