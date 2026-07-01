"""Простая система локализации для приложения «Код Мастер»."""

from typing import Dict, Optional


class Translator:
    """Хранит переводы и возвращает строку на текущем языке."""

    def __init__(self) -> None:
        self._lang = "ru"
        self._strings: Dict[str, Dict[str, str]] = {
            "ru": {},
            "en": {
                "Код Мастер": "Code Master",
                "Готов к работе": "Ready",
                "Обновить": "Update",
                "Настроить": "Settings",
                "Диагностика": "Diagnostics",
                "Выбор COM-порта": "Select COM Port",
                "COM-порт:": "COM port:",
                "Скорость:": "Baudrate:",
                "Режим эмуляции": "Emulation mode",
                "Автопереподключение": "Auto reconnect",
                "Вероятность ошибки CAN": "CAN error probability",
                "Подключить": "Connect",
                "Ошибка подключения": "Connection error",
                "Не удалось открыть порт": "Could not open port",
                "CAN Тригер": "CAN Trigger",
                "CAN Мониторинг": "CAN Monitor",
                "CAN Шлюз": "CAN Gateway",
                "Сохранить": "Save",
                "Загрузить": "Load",
                "Применить": "Apply",
                "Остановить": "Stop",
                "Старт": "Start",
                "Стоп": "Stop",
                "Очистить": "Clear",
                "Фильтр ID": "ID filter",
                "Приостановить": "Pause",
                "Отправить": "Send",
                "Циклически": "Cyclic",
                "интервал мс": "interval ms",
                "Запустить оба": "Start both",
                "Остановить оба": "Stop both",
                "Очистить всё": "Clear all",
                "Записать в CSV": "Record to CSV",
                "Остановить запись": "Stop recording",
                "Сохранить запись CAN-трафика": "Save CAN traffic recording",
                "Ошибка": "Error",
                "Не удалось открыть файл": "Could not open file",
                "Нет подключения": "No connection",
                "Порт не открыт": "Port not open",
                "Ошибка порта": "Port error",
                "Переключить светлую/тёмную тему": "Toggle light/dark theme",
                "Переключить язык": "Switch language",
                "Индикатор жизни потока чтения COM-порта": "COM reader thread heartbeat indicator",
                "COM-порт не открыт": "COM port is not open",
                "Прошивка требует реальный COM-порт": "Firmware requires real COM port",
                "Диагностика требует реальный COM-порт": "Diagnostics requires real COM port",
                "Ошибка: не указан COM-порт. Используйте --port или сохраните порт в GUI.": "Error: COM port not specified. Use --port or save port in GUI.",
                "Ошибка: не удалось открыть порт": "Error: could not open port",
                "Прошивка завершена успешно": "Firmware completed successfully",
                "Мониторинг CAN%d остановлен": "CAN%d monitoring stopped",
                "Мониторинг CAN%d запущен": "CAN%d monitoring started",
                "Принято": "Received",
                "Скорость": "Rate",
                "пак/с": "pkt/s",
                "Время": "Time",
                "Копировать ID": "Copy ID",
                "Копировать данные": "Copy data",
                "Создать триггер": "Create trigger",
                "Правила замены": "Replacement rules",
                "Игнорируемые ID": "Ignored IDs",
                "Добавить правило": "Add rule",
                "Удалить правило": "Delete rule",
                "Входной ID": "Input ID",
                "Выходной ID": "Output ID",
                "Прошивка завершена успешно": "Firmware update completed",
                "Ошибка прошивки": "Firmware error",
                "Диагностика bootloader": "Bootloader diagnostics",
                "Версия бутлоадера": "Bootloader version",
                "ID устройства": "Device ID",
                "Ошибка диагностики": "Diagnostics error",
                "Проверка обновлений": "Update check",
                "Доступно обновление": "Update available",
                "Последняя версия": "Latest version",
                "Используется последняя версия": "You are using the latest version",
                "Ошибка проверки обновлений": "Update check error",
                "Логи": "Logs",
                "Выход": "Exit",
                "Настройки": "Settings",
                "Поиск": "Search",
                "Триггеры": "Triggers",
                "Шлюз": "Gateway",
                "Библиотека": "Library",
                "Прошивка": "Firmware",
                "Готов": "Ready",
                "Индикатор подключения COM-порта": "COM port connection indicator",
            },
        }

    def set_language(self, lang: str) -> None:
        """Устанавливает текущий язык."""
        self._lang = lang if lang in self._strings else "ru"

    def get_language(self) -> str:
        """Возвращает текущий язык."""
        return self._lang

    def translate(self, text: str) -> str:
        """Возвращает перевод строки или оригинал, если перевод отсутствует."""
        return self._strings.get(self._lang, {}).get(text, text)


_translator = Translator()


def set_language(lang: str) -> None:
    _translator.set_language(lang)


def get_language() -> str:
    return _translator.get_language()


def _(text: str) -> str:
    """Возвращает перевод строки на текущем языке."""
    return _translator.translate(text)
