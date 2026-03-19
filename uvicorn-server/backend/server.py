"""
CartridgeMaster - серверная часть приложения.

Основная функциональность:
- Веб-сервер с REST API (FastAPI) для управления запасами картриджей.
- Асинхронная работа с локальной БД SQLite (aiosqlite)
- Раздача HTML/CSS/JS фронта
- AES шифрование при обмене данными с клиентским приложением на ТСД
- Отправка уведомлений на почту
"""

from fastapi import FastAPI, status, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime

import sys
import logging

import uvicorn, copy
from uvicorn.logging import DefaultFormatter
from pydantic import BaseModel
from typing import Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

from contextlib import asynccontextmanager
import time
import asyncio

import socket
import aiosqlite
import json
import base64

from db_logic import (
    init_database,
    get_cartridge_by_barcode,
    get_cartridge_name_and_quantity,
    get_cartridge_name,
    update_cartridge_quantity_add,
    update_cartridge_quantity_subtract,
    get_all_cartridges,
    get_cartridge_quantity,
    update_cartridge_quantity,
    add_history_record,
    commit_changes,
    DB_NAME as DB_NAME_IMPORT
)


AES_KEY = "My_Secret_Key_16"
DB_NAME = "inventory.db"

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

################################ Сет для временного хранения обработанных транзакций ##################################

# Хранилище уникальных ID для каждого запроса от ТСД
processed_requests = set()
# Фоновая задача для очистки старых ID (поставить потом раз в 6 часов и посмотреть сколько будет жрать ресурсов)
async def clean_ids_task():
    """
    Очищает сет processed_requests раз в несколько часов
    """
    while True:
        try:
            await asyncio.sleep(3600)
        except Exception:
            logger.error(f"Функция для очистки сета ID-транзакций не запустилась!")
        total_cleared = len(processed_requests)
        processed_requests.clear()
        logger.info(f"Набор недавних ID-транзакций от ТСД очищен. Удалено: {total_cleared}")


###################################### LIFESPAN, код выполняемый до и после запуска uvicorn в main ###################
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Установка соединения с базой
    try:
        app.state.db = await aiosqlite.connect(DB_NAME)
        logger.info("Соединение с БД установлено.")
        # Закидываем состояние в короткую переменную
        db = app.state.db
        
    except Exception as e:
        logger.error(f"Соединение с БД не установлено: {e}")
        # Выбрасываем ошибку дальше. Uvicorn её поймает и остановит запуск сервера.
        raise RuntimeError("Не удалось соединиться с базой данных!") from e

    # Запускаем инициализацию бд
    await init_database(db)

    # Запуск функции периодической очистки сета айдишников запросов от ТСД
    asyncio.create_task(clean_ids_task())

    yield
    # Логика при остановке

    await db.close()
    logger.info(f"Соединение с БД закрыто.")

############################################# FastAPI, объект app #######################################################
app = FastAPI(lifespan=lifespan)
# Монтажим папку с фронтом как /admin-ui
app.mount("/admin-ui", StaticFiles(directory="frontend", html=True))

# Нужен класс для описания структуры входящих данных.
# ТСД отправляет зашифрованный в base64 plain text, который после расшифровки представляет из себя json-структуру.
# Схема для парсинга входящего JSON: {"payload": шифрострока}
class ScanRequest(BaseModel):
    payload: str

# Схема для парсинга входящего JSON: {"change": 1} или {"new_quantity": 10, "new_min_qty": 5}
class StockChange(BaseModel):
    change: Optional[int] = None
    new_quantity: Optional[int] = None
    new_min_qty: Optional[int] = None
    new_name: Optional[str] = None

############################################### Блок шифрования ТСД #####################################################
def decrypt_payload(encrypted_b64: str):
    """
    Расшифровывает переданную строку encrypted_b64 по алгоритму AES и ключу 'AES_KEY'
    
    Args:
        encrypted_b64: строка в base64
       
    Returns:
        decrypted_bytes: расшифрованная строка в utf-8 или None
    """
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
    """
    Шифрует переданную строку data_str по алгоритму AES и ключу 'AES_KEY'
    
    Args:
        data_str: строка для шифрования
       
    Returns:
        str: строка в base64
    """
    # IV сгенерируется сам
    cipher = AES.new(AES_KEY.encode('utf-8'), AES.MODE_CBC) 
    ct_bytes = cipher.encrypt(pad(data_str.encode('utf-8'), AES.block_size))
    combined = cipher.iv + ct_bytes
    return base64.b64encode(combined).decode('utf-8')


############################################# API для ТСД ##############################################################
@app.post("/scan")
# Объект data класса ScanRequest будет заполняться данными из тела запроса
# C помощью Request получим состояние БД 
async def apiprocess_scan(data: ScanRequest, request: Request):
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
        row = await get_cartridge_by_barcode(db, req_barcode)
        if not row:
            # Устанавливаем код 404 (Not Found)
            msg = f"Штрихкод {req_barcode} не привязан!"
            return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_404_NOT_FOUND)

        # Берем id по этому штрихкоду
        cartridge_id = row[0]

        # Обновляем количество +1 в таблице cartridges
        if req_action == 'add':
            await update_cartridge_quantity_add(db, cartridge_id)

        # Обновляем количество -1 в таблице cartridges
        else:
            cursor = await update_cartridge_quantity_subtract(db, cartridge_id)
            if cursor.rowcount == 0:
                msg = "Ошибка: Остаток не может быть меньше нуля!"
                return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_409_CONFLICT)
            
        await commit_changes(db)

        # Получаем новый остаток для ответа
        result = await get_cartridge_name_and_quantity(db, cartridge_id)
        name, new_stock = result

        # Шифро-ответ ТСД: запрос обработан
        return PlainTextResponse(encrypt_payload(f"Имя: {name}\nШтрих-код:{req_barcode}\nОстаток: {new_stock}"))

    except Exception as e:
        # Шифро-ответ ТСД: непонятный косяк на сервере
        return PlainTextResponse(encrypt_payload("Непредвиденная критическая ошибка сервера!"), status_code=500)

############################################# API для браузеров #########################################################
# Просто страничка для любопытных глаз
@app.get("/scan")
async def api_get_trap_page():
    return FileResponse("frontend/pages/scan.html")

# Клиент при отправке get на сервак получает index.html вместе со скриптом app.js.
# app.js выполняется клиентом и отпр get запрос к api-сервера /api/v1/cartridges 
@app.get("/api/v1/cartridges")
async def api_get_all_cartridges(request: Request):
    # Дергаем "сохраненное" состояние подключения к базе
    db = request.app.state.db

    cartridges = await get_all_cartridges(db)
    return cartridges

@app.patch("/api/v1/cartridges/{cartridge_id}/stock")
async def api_patch_cartridge_quantity(cartridge_id: int, payload: StockChange, request: Request):
    # Собираем инфу о клиенте из request
    client_host = request.client.host
    user_agent = request.headers.get("User-Agent")
    os_info = "Platform: Windows       " if "Windows" in user_agent else "Platform: Mobile/Other  "
    client_info = os_info + client_host
    # Дергаем "сохраненное" состояние подключения к базе
    db = request.app.state.db

    # Получаем текущее количество и минимальное количество
    cursor = await db.execute("SELECT quantity, min_qty FROM cartridges WHERE id = ?", (cartridge_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Картридж не найден!")

    current_stock, current_min = row
    new_name = current_name = await get_cartridge_name(db, cartridge_id) or ""

    new_stock = current_stock
    new_min = current_min

    # Поддерживаем два вида payload:
    # - {"change": 1} (старое поведение)
    # - {"new_quantity": 10, "new_min_qty": 5, "new_name": "New Name"} (новое поведение)
    if payload.change is not None:
        new_stock = current_stock + payload.change

    if payload.new_quantity is not None:
        new_stock = payload.new_quantity

    if payload.new_min_qty is not None:
        new_min = payload.new_min_qty

    if payload.new_name is not None:
        new_name = payload.new_name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Название не может быть пустым")

    # Приводим минимальное значение к ненулевому диапазону
    if new_min < 0:
        new_min = 0

    # Не даём остатку уйти в минус
    if new_stock < 0:
        new_stock = 0
        logger.warning(f"{client_host}   - 'База не изменена, количество меньше нуля!'")
        return {"new_stock": new_stock, "min_qty": new_min}

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Обновляем таблицу cartridges
    await db.execute(
        "UPDATE cartridges SET quantity = ?, min_qty = ?, cartridge_name = ?, last_update = ? WHERE id = ?",
        (new_stock, new_min, new_name, current_time, cartridge_id)
    )

    # Записываем действие в историю, если изменилось количество
    delta = new_stock - current_stock
    if delta != 0:
        await add_history_record(db, cartridge_id, new_name, delta, client_info, current_time)

    # Подтверждаем транзакцию
    await commit_changes(db)

    logger.info(f"{client_host}   - 'Картридж {cartridge_id} обновлён. Остаток: {new_stock}, min_qty: {new_min}, name: {new_name}'")

    # Возвращаем клиенту обновлённые данные
    return {
        "new_stock": new_stock,
        "min_qty": new_min,
        "last_update": current_time
    }

@app.post("/api/v1/cartridges/{cartridge_id}/barcodes")
async def api_add_barcode(cartridge_id: int, payload: dict, request: Request):
    db = request.app.state.db
    barcode = payload.get("barcode")
    if not barcode:
        raise HTTPException(status_code=400, detail="Штрих-код обязателен")
    
    # Проверить, существует ли картридж
    cursor = await db.execute("SELECT id FROM cartridges WHERE id = ?", (cartridge_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Картридж не найден")
    
    # Проверить, не существует ли уже такой штрих-код
    cursor = await db.execute("SELECT barcode FROM barcodes WHERE barcode = ?", (barcode,))
    if await cursor.fetchone():
        raise HTTPException(status_code=409, detail="Штрих-код уже существует")
    
    # Добавить
    await db.execute("INSERT INTO barcodes (barcode, cartridge_id) VALUES (?, ?)", (barcode, cartridge_id))
    await commit_changes(db)
    return {"message": "Штрих-код добавлен"}

@app.delete("/api/v1/cartridges/{cartridge_id}/barcodes/{barcode}")
async def api_remove_barcode(cartridge_id: int, barcode: str, request: Request):
    db = request.app.state.db
    # Удалить, если существует
    cursor = await db.execute("DELETE FROM barcodes WHERE barcode = ? AND cartridge_id = ?", (barcode, cartridge_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Штрих-код не найден")
    await commit_changes(db)
    return {"message": "Штрих-код удалён"}

# Перенаправление пользователя на файл админки    
@app.get("/")
async def redirect():
    return RedirectResponse(url='/admin-ui/pages/')

# Перенаправление пользователя на файл админки
@app.get("/admin-ui")
async def redirect():
    return RedirectResponse(url='/admin-ui/pages/')


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