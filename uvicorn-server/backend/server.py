"""
CartridgeMaster - серверная часть приложения.

Основная функциональность:
- Веб-сервер с REST API (FastAPI) для управления запасами картриджей.
- Асинхронная работа с локальной БД SQLite (aiosqlite)
- Раздача HTML/CSS/JS фронта
- AES шифрование при обмене данными с клиентским приложением на ТСД
- Отправка уведомлений на почту
"""

import sys
import logging
import uvicorn, copy
from uvicorn.logging import DefaultFormatter
import socket
from server_api import app


#################################################### Логгер ###########################################################
logger = logging.getLogger("my_custom_logger")
logger.setLevel(logging.INFO)

# формат лога: 
# %(asctime)s - время
# %(levelprefix)s - раскрашенный уровень (уже содержит цвета Uvicorn)
# %(message)s - само сообщение
fmt = "%(asctime)s | %(levelprefix)s %(message)s"
date_fmt = "%Y-%m-%d %H:%M:%S"

# DefaultFormatter из uvicorn.logging
# use_colors=True для сохранения цветов
formatter = DefaultFormatter(fmt, datefmt=date_fmt, use_colors=True)

# Настраиваем Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Очищаем старые хендлеры если они были (чтобы не дублировать логи)
if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(console_handler)

hostname: str = socket.gethostname()
local_ip: str = socket.gethostbyname(hostname)

logger.info(f"Имя хоста: {hostname}")
logger.info(f"IP-адрес: {local_ip}")


###################################### Его величество main запускает uvicorn ############################################
if __name__ == "__main__":
    # Настраиваем формат: Дата Время | Уровень | Сообщение
    log_config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    # Меняем формат, добавляя %(asctime)s, НО оставляя настройки цвета
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelprefix)s %(message)s"
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s | %(levelprefix)s %(client_addr)s - '%(request_line)s' %(status_code)s"
    
    # Указываем формат даты
    log_config["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"
    log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"
    # Uvicorn слушает только запросы с сервера, на котором он запущен.
    # Сделано так, для того, чтобы нельзя было попаcть на него "в обход"
    # прокси caddy из локалки по http и 8080 порту
    uvicorn.run(app, host="127.0.0.1", port=8080, log_config=log_config)