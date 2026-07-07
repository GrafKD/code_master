"""Страница «Прошивка» для записи firmware в STM32 через UART bootloader."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.bootloader import Bootloader, BootloaderError
from core.serial_manager import SerialManager
from models.logger import get_logger
from models.translations import _ as tr

logger = get_logger(__name__)


class BootloaderWorker(QThread):
    """Фоновый поток для операций bootloader (диагностика/прошивка)."""

    progress = Signal(int)
    finished_success = Signal(str)
    finished_error = Signal(str)
    info_ready = Signal(str)

    def __init__(self, serial_manager: SerialManager, mode: str, firmware_path: str = "", parent: Optional[QWidget] = None) -> None:
        """Создаёт рабочий поток.

        Args:
            serial_manager: Менеджер COM-порта.
            mode: "diagnostics" или "flash".
            firmware_path: Путь к файлу прошивки для режима flash.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._mode = mode
        self._firmware_path = firmware_path
        self._port = None

    def run(self) -> None:
        """Выполняет bootloader-операцию в фоне."""
        try:
            self._port = self._serial_manager._port
            if self._port is None:
                raise BootloaderError(tr("COM-порт не открыт"))

            bootloader = Bootloader(self._port, progress_callback=self.progress.emit)

            if self._mode == "diagnostics":
                info = bootloader.diagnostics()
                version = info.get("version", 0)
                device_id = info.get("device_id", 0)
                self.info_ready.emit(tr("Версия bootloader: 0x{0:02X}, ID устройства: 0x{1:08X}").format(version, device_id))
            elif self._mode == "flash":
                if not self._firmware_path or not Path(self._firmware_path).exists():
                    raise BootloaderError(tr("Файл прошивки не выбран"))
                bootloader.flash_firmware(self._firmware_path)
                self.finished_success.emit(tr("Прошивка завершена успешно"))
            else:
                raise BootloaderError(tr("Неизвестный режим: {0}").format(self._mode))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка bootloader")
            self.finished_error.emit(str(exc))

    def stop(self) -> None:
        """Запрашивает остановку потока."""
        self.requestInterruption()
        self.wait(2000)


class FirmwarePage(QWidget):
    """Страница управления прошивкой STM32."""

    def __init__(self, serial_manager: SerialManager, parent: Optional[QWidget] = None) -> None:
        """Создаёт страницу прошивки.

        Args:
            serial_manager: Общий менеджер COM-порта.
            parent: Родительский виджет.
        """
        super().__init__(parent)
        self._serial_manager = serial_manager
        self._worker: Optional[BootloaderWorker] = None
        self._create_widgets()
        self._build_layout()

    def _create_widgets(self) -> None:
        """Создаёт элементы управления страницы."""
        font = QFont("Segoe UI", 10)

        self._title = QLabel(tr("Прошивка STM32"))
        self._title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title.setProperty("title", True)

        self._subtitle = QLabel(tr("Загрузка .bin файла через UART bootloader (AN3155)"))
        self._subtitle.setFont(QFont("Segoe UI", 11))

        self._file_edit = QLineEdit()
        self._file_edit.setFont(font)
        self._file_edit.setPlaceholderText(tr("Путь к .bin файлу"))

        self._browse_button = QPushButton(tr("Обзор"))
        self._browse_button.setFixedSize(90, 28)
        self._browse_button.setFont(font)
        self._browse_button.clicked.connect(self._on_browse)

        self._info_button = QPushButton(tr("Инфо"))
        self._info_button.setFixedSize(90, 28)
        self._info_button.setFont(font)
        self._info_button.clicked.connect(self._on_info)

        self._flash_button = QPushButton(tr("Загрузить"))
        self._flash_button.setFixedSize(110, 30)
        self._flash_button.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._flash_button.clicked.connect(self._on_flash)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFont(font)

        self._status_label = QLabel("")
        self._status_label.setFont(font)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)

    def _build_layout(self) -> None:
        """Собирает компоновку страницы."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)

        file_layout = QHBoxLayout()
        file_layout.setSpacing(8)
        file_layout.addWidget(self._file_edit)
        file_layout.addWidget(self._browse_button)
        layout.addLayout(file_layout)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        buttons_layout.addWidget(self._info_button)
        buttons_layout.addWidget(self._flash_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        layout.addWidget(self._progress)
        layout.addWidget(self._status_label)
        layout.addStretch()

    def _on_browse(self) -> None:
        """Открывает диалог выбора файла прошивки."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Выбор файла прошивки"),
            "",
            tr("Firmware files (*.bin *.hex);;All files (*.*)"),
        )
        if path:
            self._file_edit.setText(path)

    def _set_status(self, text: str, error: bool = False) -> None:
        """Устанавливает текст статуса с цветом."""
        self._status_label.setText(text)
        color = "#F44336" if error else "#4CAF50"
        self._status_label.setStyleSheet(f"color: {color};")

    def _start_worker(self, mode: str, firmware_path: str = "") -> None:
        """Запускает фоновую операцию bootloader."""
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(self, tr("Внимание"), tr("Операция уже выполняется"))
            return

        if not self._serial_manager.is_open():
            self._set_status(tr("COM-порт не открыт. Подключитесь в мастере подключения."), error=True)
            return

        self._progress.setValue(0)
        self._set_status(tr("Выполнение..."))
        self._flash_button.setEnabled(False)
        self._info_button.setEnabled(False)

        self._worker = BootloaderWorker(self._serial_manager, mode, firmware_path, self)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished_success.connect(self._on_success)
        self._worker.finished_error.connect(self._on_error)
        self._worker.info_ready.connect(self._on_info_ready)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_info(self) -> None:
        """Запускает диагностику bootloader."""
        self._start_worker("diagnostics")

    def _on_flash(self) -> None:
        """Запускает загрузку прошивки."""
        path = self._file_edit.text().strip()
        if not path:
            self._set_status(tr("Выберите файл прошивки"), error=True)
            return
        self._start_worker("flash", path)

    def _on_success(self, message: str) -> None:
        """Обрабатывает успешное завершение операции."""
        self._set_status(message)
        QMessageBox.information(self, tr("Готово"), message)

    def _on_error(self, message: str) -> None:
        """Обрабатывает ошибку операции."""
        self._set_status(message, error=True)
        QMessageBox.critical(self, tr("Ошибка"), message)

    def _on_info_ready(self, message: str) -> None:
        """Отображает информацию от bootloader."""
        self._set_status(message)

    def _on_worker_finished(self) -> None:
        """Восстанавливает кнопки после завершения потока."""
        self._flash_button.setEnabled(True)
        self._info_button.setEnabled(True)
        self._worker = None
