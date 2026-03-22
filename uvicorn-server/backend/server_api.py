"""
CartridgeMaster - API эндпоинты сервера.

Содержит все REST API эндпоинты, модели данных и вспомогательные функции.
"""

from fastapi import FastAPI, status, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime

import logging

from pydantic import BaseModel
from typing import Optional

from contextlib import asynccontextmanager
import time
import asyncio

import aiosqlite
import json
from config import DB_NAME

from server_cipher import decrypt_payload, encrypt_payload

from server_db import (
    init_database,
    get_cartridge_by_barcode,
    get_cartridge_name_and_quantity,
    get_cartridge_name,
    update_cartridge_quantity_add,
    update_cartridge_quantity_subtract,
    get_all_cartridges,
    get_cartridge_quantity,
    update_cartridge_quantity,
    get_cartridge_by_id,
    get_cartridge_stock_and_min,
    update_cartridge_details,
    barcode_exists,
    add_barcode,
    remove_barcode,
    add_history_record,
    commit_changes
)

logger = logging.getLogger("my_custom_logger")

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

# Схема для парсинга входящего JSON: {"new_quantity": 10, "new_min_qty": 5, "new_name": "New Name"}
class StockChange(BaseModel):
    new_quantity: Optional[int] = None
    new_min_qty: Optional[int] = None
    new_name: Optional[str] = None


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
        return PlainTextResponse(encrypt_payload(f"Имя: {name}\nШтрих-код:{req_barcode}\nОстаток: {new_stock}"), status_code=status.HTTP_200_OK)

    except Exception as e:
        # Шифро-ответ ТСД: непонятный косяк на сервере
        return PlainTextResponse(encrypt_payload("Непредвиденная критическая ошибка сервера!"), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    row = await get_cartridge_stock_and_min(db, cartridge_id)
    if not row:
        raise HTTPException(status_code=404, detail="Картридж не найден!")

    current_stock, current_min = row
    new_name = await get_cartridge_name(db, cartridge_id) or ""

    new_stock = current_stock
    new_min = current_min

    # Обновляем поля на основе payload
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
    await update_cartridge_details(db, cartridge_id, new_stock, new_min, new_name, current_time)

    # Записываем действие в историю, если изменилось количество
    delta = new_stock - current_stock
    if delta != 0:
        await add_history_record(db, cartridge_id, new_name, delta, client_info, current_time)

    # Подтверждаем транзакцию
    await commit_changes(db)

    logger.info(f"{client_host}   - 'ID: {cartridge_id} | Имя: {new_name} | Дельта: {delta} | Кол-во: {new_stock} | Минимум: {new_min}'")

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
    if not await get_cartridge_by_id(db, cartridge_id):
        raise HTTPException(status_code=404, detail="Картридж не найден")

    # Проверить, не существует ли уже такой штрих-код
    if await barcode_exists(db, barcode):
        raise HTTPException(status_code=409, detail="Штрих-код уже существует")

    # Добавить
    await add_barcode(db, barcode, cartridge_id)
    await commit_changes(db)
    return {"message": "Штрих-код добавлен"}

@app.delete("/api/v1/cartridges/{cartridge_id}/barcodes/{barcode}")
async def api_remove_barcode(cartridge_id: int, barcode: str, request: Request):
    db = request.app.state.db
    # Удалить, если существует
    deleted = await remove_barcode(db, barcode, cartridge_id)
    if deleted == 0:
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