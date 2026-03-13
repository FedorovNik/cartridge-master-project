from fastapi import FastAPI, status, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime

import sys
import logging

import uvicorn, copy
from uvicorn.logging import DefaultFormatter
from pydantic import BaseModel

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

from contextlib import asynccontextmanager
import time
import asyncio

import socket
import aiosqlite
import json
import base64


AES_KEY = "My_Secret_Key_16"
DB_NAME = "inventory.db"

############################################## ЛОГГЕР #############################################################
# 1. Создаем логгер
logger = logging.getLogger("my_custom_logger")
logger.setLevel(logging.INFO)

# формат лога: 
# %(asctime)s - время
# %(levelprefix)s - раскрашенный уровень (уже содержит цвета Uvicorn)
# %(message)s - само сообщение
fmt = "%(asctime)s | %(levelprefix)s %(message)s"
date_fmt = "%Y-%m-%d %H:%M:%S"

# Используем именно DefaultFormatter из uvicorn.logging
# use_colors=True для сохранения цветов
formatter = DefaultFormatter(fmt, datefmt=date_fmt, use_colors=True)

# Настраиваем Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Очищаем старые хендлеры, если они были (чтобы не дублировать логи)
if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(console_handler)

hostname: str = socket.gethostname()
local_ip: str = socket.gethostbyname(hostname)

logger.info(f"Имя хоста: {hostname}")
logger.info(f"IP-адрес: {local_ip}")

############################################## ЛОГГЕР #############################################################
# Хранилище уникальных ID для каждого запроса от ТСД
processed_requests = set()

# Фоновая задача для очистки старых ID (раз в 6 часов, для тестов каждые 10 сек)
async def clean_ids_task():
    while True:
        try:
            await asyncio.sleep(3600)
        except Exception:
            logger.error(f"Функция для очистки сета ID-транзакций не запустилась!")
        total_cleared = len(processed_requests)
        processed_requests.clear()
        logger.info(f"Набор недавних ID-транзакций от ТСД очищен. Удалено: {total_cleared}")

# Lifespan - механизм управления жизненным циклом приложения, 
# который позволяет выполнять код перед началом работы приложения и после
@asynccontextmanager
async def lifespan(app: FastAPI):
    ############ Установка соединения с базой ##########################
    try:
        app.state.db = await aiosqlite.connect(DB_NAME)
        # WAL для конкурентного доступа, но мб это избыточно
        await app.state.db.execute("PRAGMA journal_mode=WAL;")
        logger.info("Соединение с БД установлено.")
        # Закидываем в короткую переменную
        db = app.state.db
        
    except Exception as e:
        logger.error(f"Соединение с БД не установлено: {e}")
        # Выбрасываем ошибку дальше. Uvicorn её поймает и остановит запуск сервера.
        raise RuntimeError("Не удалось соединиться с базой данных!") from e

    ############ Создание таблиц в базе если не существуют ############
    # Картриджи
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cartridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cartridge_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            min_qty INTEGER DEFAULT 0,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Штрихкоды
    await db.execute("""
        CREATE TABLE IF NOT EXISTS barcodes (
            barcode TEXT PRIMARY KEY,
            cartridge_id INTEGER NOT NULL,
            FOREIGN KEY (cartridge_id) REFERENCES cartridges(id)
        )
    """)
    # История изменений
    await db.execute("""
        CREATE TABLE IF NOT EXISTS history (
            increment INTEGER PRIMARY KEY AUTOINCREMENT,
            cartridge_id INTEGER NOT NULL,
            cartridge_name TEXT NOT NULL,
            delta INTEGER NOT NULL,
            editor TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cartridge_id) REFERENCES cartridges(id)
        )
    """)
    logger.info(f"База данных проинициализована.")
    await db.commit()

    # Запуск при старте функции очистки сета айдишников транзакций ТСД
    asyncio.create_task(clean_ids_task())

    yield

    # Логика при остановке
    await db.close()
    logger.info(f"Соединение с БД закрыто.")


app = FastAPI(lifespan=lifespan)
# Монтажим папку с фронтом как /admin-ui
app.mount("/admin-ui", StaticFiles(directory="frontend", html=True))


# В FastApi нужен класс для описания структуры входящих данных.
# ТСД отправляет зашифрованный в base64 plain text, который после расшифровки представляет из себя json-структуру.
# Схема для парсинга входящего JSON: {"payload": шифрострока}
class ScanRequest(BaseModel):
    payload: str

# Схема для парсинга входящего JSON: {"change": 1} или {"change": -1}
class StockChange(BaseModel):
    change: int

######################################### ШИФРАТОР И ДЕШИФРАТОР ДЛЯ ТСД ################################################
def decrypt_payload(encrypted_b64: str):
    try:
        # Декодируем из Base64
        combined = base64.b64decode(encrypted_b64)
        # Извлекаем IV (первые 16 байт) и зашифрованные данные
        iv = combined[:16]
        ciphertext = combined[16:]
        # Настраиваем AES CBC
        cipher = AES.new(AES_KEY.encode('utf-8'), AES.MODE_CBC, iv)
        # Расшифровываем и убираем Padding
        decrypted_bytes = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"Ошибка расшифровки: {e}")
        return None
    
# Шифратор для ответа ТСД
def encrypt_payload(data_str: str):
    # IV сгенерируется сам
    cipher = AES.new(AES_KEY.encode('utf-8'), AES.MODE_CBC) 
    ct_bytes = cipher.encrypt(pad(data_str.encode('utf-8'), AES.block_size))
    combined = cipher.iv + ct_bytes
    return base64.b64encode(combined).decode('utf-8')


############################################# API для ТСД ##############################################################
@app.post("/scan")
# Объект data класса ScanRequest будет заполняться данными из тела запроса
# C помощью Request получим состояние БД 
async def process_scan(data: ScanRequest, request: Request):
    # Получаем объект базы
    db = request.app.state.db

    # Отправляем в дешифратор абракадабру, которая должна быть расшифрована в JSON-строки
    decrypted_json_str = decrypt_payload(data.payload)

    # Если функция дешифратор ничего не вернула..
    if not decrypted_json_str:
        return PlainTextResponse(
            encrypt_payload("Ошибка: AES-Ключ не совпадал на сервере или пакет поврежден!"),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # Если расшифровалась, парсим полученный json
    try:
        inner_data = json.loads(decrypted_json_str)
        # ТСДшник формирует уникальный ID у каждого запроса
        req_id = inner_data.get('id')
        # ТСДшник передает время, когда было сформировано тело запроса
        req_time = inner_data.get('time', 0)

        # Защита от Reply-атаки:
        # Изначальная проблема: содержимое пакета (в виде {payload: base64} ) можно стащить снифером и отправить серверу опять.
        # Гениальное и удивительно простое решение!
        # Полученный пакет действителен 10 секунд с момента генерации и только если его НЕТ в сете processed_requests.
        # Кул-хацкер может успеть за 10 секунд скопировать содержимое пакета и отправить серверу еще раз, 
        # но сервер этот пакет уже обработал и занёс айдишник из тела json в processed_requests.
        # processed_requests чистится, поэтому дополнительно нужна еще и проверка на время (10 секунд), 
        # чтобы нельзя было отправить "протухшие" запросы через время, когда в processed_requests этого айдишника не будет.
        
        now = int(time.time())
        # Меньше 10 секунд лучше не ставить, иначе если на тсдшнике быстро спамить запросами на серв,
        # тсд будет получать ответ о том, что он запросы шлет просроченные.
        # Скорее всего это проблема в сетевой задержке и дрейфе времени на разных устройствах.
        if abs(now - req_time) > 10:
            # Шифро-ответ можно вообще не отправлять на такие "приколы", но пусть будет для наглядности
            return PlainTextResponse(encrypt_payload("Ошибка: Запрос просрочен!"), status_code=403)
        
        if req_id in processed_requests:
            return PlainTextResponse(encrypt_payload("Ошибка: Повторный запрос!"), status_code=403)

        # Если не дропнули такой запрос, то этот пакет 100% от ТСД, заносим айдишник в сет 
        processed_requests.add(req_id)

        # Продолжаем обработку нормального запроса
        # ТСД присылает 'barcode': '1234567891111'
        req_barcode = inner_data.get('barcode')
        # ТСД присылает 'action': 'add' или 'red'
        req_action = inner_data.get('action') 
        
        # Ищем штрихкод
        cursor = await db.execute("SELECT cartridge_id FROM barcodes WHERE barcode = ?", (req_barcode,))
        row = await cursor.fetchone()
        if not row:
            # Устанавливаем код 404 (Not Found)
            msg = f"Штрихкод {req_barcode} не привязан!"
            return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_404_NOT_FOUND)

        # Берем id по этому штрихкоду
        cartridge_id = row[0]

        # Обновляем количество +1 в таблице cartridges
        if req_action == 'add':
            await db.execute("UPDATE cartridges SET quantity = quantity + 1 WHERE id = ?", (cartridge_id,))

        # Обновляем количество -1 в таблице cartridges
        else:
            cursor = await db.execute("UPDATE cartridges SET quantity = quantity - 1 WHERE id = ? AND stock > 0", (cartridge_id,))
            if cursor.rowcount == 0:
                msg = "Ошибка: Остаток не может быть меньше нуля!"
                return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_409_CONFLICT)
            
        await db.commit()

        # Получаем новый остаток для ответа
        cursor = await db.execute("SELECT cartridge_name, quantity FROM cartridges WHERE id = ?", (cartridge_id,))
        name, new_stock = await cursor.fetchone()

        # Шифро-ответ ТСД: запрос обработан
        return PlainTextResponse(encrypt_payload(f"Имя: {name}\nШтрих-код:{req_barcode}\nОстаток: {new_stock}"))

    except Exception as e:
        # Шифро-ответ ТСД: непонятный косяк на сервере
        return PlainTextResponse(encrypt_payload("Непредвиденная критическая ошибка сервера!"), status_code=500)

################################## API для браузеров #############################################################
# Джокушка локера от любопытных глаз
@app.get("/scan")
async def trap_page():
    return FileResponse("frontend/pages/scan.html")

# Клиент при отправке get на сервак получает index.html вместе со скриптом app.js.
# app.js выполняет get запрос к api-сервера /api/v1/cartridges 
@app.get("/api/v1/cartridges")
async def get_inventory(request: Request):
    db = request.app.state.db
    # волшебный запрос к базе
    cursor = await db.execute("""
        SELECT 
            c.id, 
            c.cartridge_name,
            c.quantity,
            c.min_qty,
            c.last_update, 
            GROUP_CONCAT(DISTINCT b.barcode) as barcodes
        FROM cartridges c
        LEFT JOIN barcodes b ON c.id = b.cartridge_id
        GROUP BY c.id
    """)
    rows = await cursor.fetchall()
    # Возвращаем чистый json
    return [
        {
            "id": r[0],
            "name": r[1],
            "quantity": r[2],
            "min_qty": r[3],
            "last_update": r[4],
            "barcodes": r[5].split(",") if r[4] else []
            
        } for r in rows
    ]

@app.patch("/api/v1/cartridges/{cartridge_id}/stock")
async def update_cartridge_stock(cartridge_id: int, payload: StockChange, request: Request):
    # Собираем инфу о клиенте из request
    client_host = request.client.host
    user_agent = request.headers.get("User-Agent")
    os_info = "Platform: Windows       " if "Windows" in user_agent else "Platform: Mobile/Other  "
    client_info = os_info + client_host
    # Дергаем "сохраненное" состояние подключения к базе
    db = request.app.state.db
    # Получаем текущее количество
    async with db.execute(
        "SELECT quantity FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Картридж не найден!")
        
        current_stock = row[0]
    
    # Вычисляем новый остаток и не даем ему уйти в минус
    new_stock = current_stock + payload.change
    if new_stock < 0:
        new_stock = 0
        logger.warning(f"{client_host}   - 'База не изменена, количество меньше нуля!'")
        return {"new_stock": new_stock}
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Обновляем таблицу cartridges
    await db.execute(
        "UPDATE cartridges SET quantity = ?, last_update = ? WHERE id = ?", 
        (new_stock, current_time, cartridge_id)
    )
    
    # Записываем действие в update_history для сохранения истории движения
    # Структура полей может немного отличаться в зависимости от твоей схемы, 
    # здесь пример записи ID картриджа, изменения и итогового остатка
    async with db.execute(
        "SELECT cartridge_name FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Косяк!")
        
        cartridge_name = row[0]

    await db.execute(
        """
        INSERT INTO history (cartridge_id, cartridge_name, delta, editor, created_at) 
        VALUES (?, ?, ?, ?, ?)
        """, 
        (cartridge_id, cartridge_name, payload.change, client_info, current_time)
    )
    
    # Подтверждаем транзакцию
    await db.commit()

    
    logger.info(f"{client_host}   - 'Картридж {cartridge_name} изменен на {payload.change}. Новый остаток: {new_stock}'")
    
    # 5. Возвращаем клиенту обновленное значение
    return {
        "new_stock": new_stock,
        "last_update": current_time
    }

# Перенаправление пользователя на файл админки    
@app.get("/")
async def root_redirect():
    return RedirectResponse(url='/admin-ui/pages/')

# Перенаправление пользователя на файл админки
@app.get("/admin-ui")
async def root_redirect():
    return RedirectResponse(url='/admin-ui/pages/')


################################## ЗАПУСК UVICORN #############################################################
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