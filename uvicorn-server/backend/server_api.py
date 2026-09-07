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
    get_cartridge_barcodes,
    get_cartridge_name_and_quantity,
    get_cartridge_info,
    get_cartridge_name,
    update_cartridge_quantity_add,
    update_cartridge_quantity_subtract,
    update_cartridge_timestamp,
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
    get_yearly_expense_heatmap,
    commit_changes,
    create_session,
    get_session,
    delete_session,
    cleanup_expired_sessions,
    create_cartridge,
    delete_cartridge,
    get_all_emails,
    add_email,
    update_email_notifications,
    delete_email,
    get_emails_for_notifications,
    get_low_stock_cartridges,
    get_setting,
    set_setting,
    get_notification_schedule,
    set_notification_schedule,
    get_notifications_enabled,
    set_notifications_enabled
)

from server_post import send_low_stock_notifications

from server_auth import authenticate_user

# Модели для аутентификации
class LoginRequest(BaseModel):
    username: str
    password: str
    auth_type: str = 'ldap'  # 'ldap' или 'local'

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

# Фоновая задача для очистки истекших сессий
async def clean_expired_sessions_task(db):
    """
    Очищает истекшие сессии каждый час
    """
    while True:
        try:
            await asyncio.sleep(3600)  # Каждый час
            await cleanup_expired_sessions(db)
            logger.info("Истекшие сессии очищены")
        except Exception as e:
            logger.error(f"Ошибка при очистке сессий: {e}")


async def check_notification_schedule_task():
    """
    Проверяет расписание отправки уведомлений каждую минуту
    """
    from datetime import datetime
    
    last_sent_date = None  # Отслеживаем дату последней отправки для предотвращения дублей
    
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждую минуту
            
            async with aiosqlite.connect(DB_NAME) as db:
                # Проверяем, включены ли уведомления глобально
                enabled = await get_notifications_enabled(db)
                if not enabled:
                    continue  # Уведомления выключены
                
                schedule = await get_notification_schedule(db)
                
                if not schedule:
                    continue  # Расписание не установлено
                
                current_time = datetime.now()
                current_day = current_time.weekday()  # 0=Monday, 6=Sunday
                current_time_hm = current_time.strftime("%H:%M")
                
                # Получаем список дней из строки
                days_str = schedule["days_of_week"]
                if not days_str:
                    continue
                
                schedule_days = [int(d.strip()) for d in days_str.split(',')]
                
                # Преобразуем дни в weekday формат (0=Monday, 6=Sunday)
                converted_days = []
                for day in schedule_days:
                    if day == 0:  # Воскресенье (0 в нашей системе)
                        converted_days.append(6)
                    else:
                        converted_days.append(day - 1)
                
                schedule_time = schedule["time_hm"]
                
                # Проверяем совпадение дня недели и времени
                if current_day in converted_days and current_time_hm == schedule_time:
                    # Проверяем, что уведомление не отправлялось сегодня
                    today_str = current_time.date().isoformat()
                    if last_sent_date != today_str:
                        # Отправляем уведомления
                        emails = await get_emails_for_notifications(db)
                        if emails:
                            low_stock = await get_low_stock_cartridges(db)
                            if low_stock:
                                await send_low_stock_notifications(emails, low_stock)
                                logger.info(f"Автоматическое уведомление отправлено {len(emails)} адресам")
                        
                        last_sent_date = today_str
                
        except Exception as e:
            logger.error(f"Ошибка при проверке расписания уведомлений: {e}")


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
    
    # Запуск функции периодической очистки истекших сессий
    asyncio.create_task(clean_expired_sessions_task(db))
    
    # Запуск функции проверки расписания отправки уведомлений
    asyncio.create_task(check_notification_schedule_task())

    yield
    # Логика при остановке

    await db.close()
    logger.info(f"Соединение с БД закрыто.")

############################################# FastAPI, объект app #######################################################
app = FastAPI(lifespan=lifespan)

# Middleware для проверки сессий
@app.middleware("http")
async def session_middleware(request: Request, call_next):
    # Пропускаем эндпоинты логина и статические файлы
    if request.url.path.startswith("/api/v1/login") or request.url.path.startswith("/admin-ui"):
        response = await call_next(request)
        return response
    
    # Проверяем сессию для API эндпоинтов
    if request.url.path.startswith("/api/"):
        session_id = request.cookies.get("session_id")
        if not session_id:
            return PlainTextResponse("Unauthorized", status_code=401)
        
        db = request.app.state.db
        session = await get_session(db, session_id)
        if not session:
            return PlainTextResponse("Unauthorized", status_code=401)
    
    response = await call_next(request)
    return response

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
    new_quantity_reserve: Optional[int] = None
    new_name: Optional[str] = None

# Схема для создания нового картриджа
class CartridgeCreateRequest(BaseModel):
    cartridge_name: str
    quantity: int
    quantity_reserve: int
    min_qty: int
    barcode: str

# Схемы для email уведомлений
class EmailAddRequest(BaseModel):
    email_address: str

class EmailUpdateRequest(BaseModel):
    notifications_on: bool

# Схемы для настроек
class SettingUpdateRequest(BaseModel):
    value: str


############################################# API для аутентификации ##################################################
@app.post("/api/v1/login")
async def login(data: LoginRequest, request: Request):
    from fastapi.responses import Response
    db = request.app.state.db
    
    # Проверяем пользователя через выбранный метод аутентификации
    success, user_dn = authenticate_user(data.username, data.password, data.auth_type)
    if not success:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Создаем сессию
    session_id = await create_session(db, user_dn)
    
    # Устанавливаем куку с session_id
    response = Response("Login successful")
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=604800)  # 7 дней
    return response


@app.post("/api/v1/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        db = request.app.state.db
        await delete_session(db, session_id)
    
    response = PlainTextResponse("Logged out")
    response.delete_cookie("session_id")
    return response


@app.get("/api/v1/me")
async def get_me(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    db = request.app.state.db
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user_dn, _ = session
    return {"user_dn": user_dn}


############################################# API для ТСД ##############################################################
@app.post("/scan")
# Объект data класса ScanRequest будет заполняться данными из тела запроса
# C помощью Request получим состояние БД 
async def apiprocess_scan(data: ScanRequest, request: Request):
    # Собираем инфу о клиенте из request
    client_host = request.client.host
    user_agent = request.headers.get("User-Agent")
    os_info = "Platform: Windows       " if "Windows" in user_agent else "Platform: Mobile/Other  "
    client_info = os_info + client_host
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
            msg = f"Абракадабра, абра-у-на-на!\nТакого штрих-кода нет в базе:\n{req_barcode}"

            return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_404_NOT_FOUND)

        # Берем id по этому штрихкоду
        cartridge_id = row[0]

        if req_action == 'getinfo':
            info = await get_cartridge_info(db, cartridge_id)
            if not info:
                return PlainTextResponse(
                    encrypt_payload(f"Картридж для штрихкода {req_barcode} не найден!"),
                    status_code=status.HTTP_404_NOT_FOUND
                )

            _, name, quantity, min_qty, last_update, quantity_reserve = info
            barcodes = await get_cartridge_barcodes(db, cartridge_id)
            barcode_lines = "\n".join(f"Штрих-код: {barcode}" for barcode in barcodes)
            message = (
                f"Имя: {name}\n"
                f"Количество: {quantity}\n"
                f"Минимальный остаток: {min_qty}\n"
                f"Резерв: {quantity_reserve or 0}\n"
                f"{barcode_lines}\n"
                f"Дата обновления: {last_update or 'нет данных'}"
            )
            return PlainTextResponse(encrypt_payload(message), status_code=status.HTTP_200_OK)

        if req_action not in ('add', 'red'):
            return PlainTextResponse(
                encrypt_payload("Ошибка: Неизвестное действие запроса!"),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Текущее время
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Обновляем количество +1 в таблице cartridges
        if req_action == 'add':
            await update_cartridge_quantity_add(db, cartridge_id)
        # Обновляем количество -1 в таблице cartridges
        else:
            cursor = await update_cartridge_quantity_subtract(db, cartridge_id)
            if cursor.rowcount == 0:
                msg = "Ошибка: Остаток не может быть меньше нуля!"
                return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_409_CONFLICT)

        await update_cartridge_timestamp(db, cartridge_id, current_time)
                  
        # Получаем новый остаток и имя для ответа
        result = await get_cartridge_name_and_quantity(db, cartridge_id)
        name, new_stock = result

        # Обновление таблицы с историей
        if req_action == 'add':
            await add_history_record(db,cartridge_id,name,1,client_info,current_time)
            logger.info(f"{client_host}   - 'TSD  ID: {cartridge_id} | Имя: {name} | Дельта:  1 | Кол-во: {new_stock}'")
        else:
            await add_history_record(db,cartridge_id,name,-1,client_info,current_time)
            logger.info(f"{client_host}   - 'TSD  ID: {cartridge_id} | Имя: {name} | Дельта: -1 | Кол-во: {new_stock}'")

        await commit_changes(db)

        # Шифро-ответ ТСД: запрос обработан
        operation_name = "Добавление картриджа" if req_action == 'add' else "Расход картриджа"
        message = (
            f"Операция: {operation_name}\n"
            f"Дата и время: {current_time}\n"
            f"Имя: {name}\n"
            f"Штрих-код: {req_barcode}\n"
            f"Остаток: {new_stock}\n"
        )
        return PlainTextResponse(encrypt_payload(message), status_code=status.HTTP_200_OK)

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

    # Получаем имя пользователя из сессии
    session_id = request.cookies.get("session_id")
    username = None
    if session_id:
        session_data = await get_session(db, session_id)
        if session_data:
            user_dn = session_data[0]
            # Извлекаем имя пользователя из DN
            if "cn=" in user_dn:
                username = user_dn.split("cn=")[1].split(",")[0]
            else:
                username = user_dn

    # Получаем текущее количество и минимальное количество
    row = await get_cartridge_stock_and_min(db, cartridge_id)
    if not row:
        raise HTTPException(status_code=404, detail="Картридж не найден!")

    current_stock, current_min, current_reserve = row
    new_name = await get_cartridge_name(db, cartridge_id) or ""

    new_stock = current_stock
    new_min = current_min
    new_reserve = current_reserve

    # Обновляем поля на основе payload
    if payload.new_quantity is not None:
        new_stock = payload.new_quantity

    if payload.new_quantity_reserve is not None:
        new_reserve = payload.new_quantity_reserve

    if payload.new_min_qty is not None:
        new_min = payload.new_min_qty

    if payload.new_name is not None:
        new_name = payload.new_name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Название не может быть пустым")

    # Приводим минимальное значение к ненулевому диапазону
    if new_min < 0:
        new_min = 0
    
    if new_reserve < 0:
        new_reserve = 0

    # Не даём остатку уйти в минус
    if new_stock < 0:
        new_stock = 0
        logger.warning(f"{client_host}   - 'База не изменена, количество меньше нуля!'")
        return {"new_stock": new_stock, "min_qty": new_min, "new_quantity_reserve": new_reserve}

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Обновляем таблицу cartridges
    await update_cartridge_details(db, cartridge_id, new_stock, new_min, new_name, new_reserve, current_time)

    # Записываем действие в историю, если изменилось количество
    delta = new_stock - current_stock
    if delta != 0:
        await add_history_record(db, cartridge_id, new_name, delta, client_info, current_time, username)

    # Подтверждаем транзакцию
    await commit_changes(db)

    logger.info(f"{client_host}   - 'ID: {cartridge_id} | Имя: {new_name} | Дельта: {delta} | Кол-во: {new_stock} | Минимум: {new_min} | Резерв: {new_reserve}'")

    # Возвращаем клиенту обновлённые данные
    return {
        "new_stock": new_stock,
        "min_qty": new_min,
        "new_quantity_reserve": new_reserve,
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


@app.get("/api/v1/history/expenses/heatmap")
async def api_get_expenses_heatmap(request: Request, year: Optional[int] = None):
    """
    Возвращает данные для тепловой карты расходов по картриджам.
    В расчет попадают только отрицательные значения delta из history.
    """
    selected_year = year or datetime.now().year
    db = request.app.state.db

    result = await get_yearly_expense_heatmap(db, selected_year)
    total_spent = 0
    for series_item in result["series"]:
        for point in series_item["data"]:
            total_spent += point["y"]

    available_years = result["available_years"]
    if selected_year not in available_years:
        available_years.insert(0, selected_year)
        available_years = sorted(set(available_years), reverse=True)

    return {
        "selected_year": selected_year,
        "available_years": available_years,
        "series": result["series"],
        "total_spent": total_spent
    }


################################ API для email уведомлений ###################################################

@app.get("/api/v1/emails")
async def get_emails(request: Request):
    """
    Получить все email адреса для уведомлений
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            emails = await get_all_emails(db)
            return {"emails": emails}
    except Exception as e:
        logger.error(f"Ошибка при получении email адресов: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/v1/emails")
async def add_new_email(email_data: EmailAddRequest, request: Request):
    """
    Добавить новый email адрес
    """
    try:
        # Валидация email (простая проверка)
        import re
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email_data.email_address):
            raise HTTPException(status_code=400, detail="Неверный формат email адреса")

        async with aiosqlite.connect(DB_NAME) as db:
            email_id = await add_email(db, email_data.email_address)
            if email_id is None:
                raise HTTPException(status_code=409, detail="Email адрес уже существует")
            await commit_changes(db)
            return {"message": "Email адрес добавлен", "id": email_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при добавлении email: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.patch("/api/v1/emails/{email_id}")
async def update_email(email_id: int, email_data: EmailUpdateRequest, request: Request):
    """
    Обновить настройки уведомлений для email
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await update_email_notifications(db, email_id, email_data.notifications_on)
            await commit_changes(db)
            return {"message": "Настройки уведомлений обновлены"}
    except Exception as e:
        logger.error(f"Ошибка при обновлении email: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.delete("/api/v1/emails/{email_id}")
async def remove_email(email_id: int, request: Request):
    """
    Удалить email адрес
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            deleted_count = await delete_email(db, email_id)
            if deleted_count == 0:
                raise HTTPException(status_code=404, detail="Email адрес не найден")
            await commit_changes(db)
            return {"message": "Email адрес удален"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении email: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/v1/emails/send-notifications")
async def send_notifications(request: Request):
    """
    Отправить уведомления о низком запасе картриджей
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            # Получить email адреса для уведомлений
            emails = await get_emails_for_notifications(db)
            if not emails:
                return {"message": "Нет email адресов для уведомлений"}

            # Получить картриджи с низким запасом
            low_stock = await get_low_stock_cartridges(db)
            if not low_stock:
                return {"message": "Нет картриджей с низким запасом"}

            # Отправить уведомления
            sent_count = await send_low_stock_notifications(emails, low_stock)
            return {"message": f"Уведомления отправлены на {sent_count} адресов"}
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


################################ API для настроек ###################################################

@app.get("/api/v1/settings/{key}")
async def get_setting_value(key: str, request: Request):
    """
    Получить значение настройки
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            value = await get_setting(db, key)
            return {"key": key, "value": value}
    except Exception as e:
        logger.error(f"Ошибка при получении настройки {key}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.put("/api/v1/settings/{key}")
async def update_setting(key: str, setting_data: SettingUpdateRequest, request: Request):
    """
    Обновить значение настройки
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await set_setting(db, key, setting_data.value)
            await commit_changes(db)
            return {"message": "Настройка обновлена"}
    except Exception as e:
        logger.error(f"Ошибка при обновлении настройки {key}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


################################ API для расписания уведомлений ###################################################

class NotificationScheduleRequest(BaseModel):
    days_of_week: str
    time_hm: str


@app.get("/api/v1/notification-schedule")
async def get_notification_schedule_endpoint(request: Request):
    """
    Получить расписание отправки уведомлений
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            schedule = await get_notification_schedule(db)
            if schedule:
                return schedule
            else:
                return {"days_of_week": None, "time_hm": None}
    except Exception as e:
        logger.error(f"Ошибка при получении расписания: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/v1/notification-schedule")
async def set_notification_schedule_endpoint(schedule_data: NotificationScheduleRequest, request: Request):
    """
    Установить расписание отправки уведомлений
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await set_notification_schedule(db, schedule_data.days_of_week, schedule_data.time_hm)
            await commit_changes(db)
            return {"message": "Расписание уведомлений установлено"}
    except ValueError as e:
        logger.error(f"Ошибка валидации расписания: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при установке расписания: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.get("/api/v1/notifications-enabled")
async def get_notifications_enabled_endpoint(request: Request):
    """
    Получить статус глобальной настройки уведомлений
    """
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            enabled = await get_notifications_enabled(db)
            return {"enabled": enabled}
    except Exception as e:
        logger.error(f"Ошибка при получении статуса уведомлений: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/v1/notifications-enabled")
async def set_notifications_enabled_endpoint(enabled_data: dict, request: Request):
    """
    Установить статус глобальной настройки уведомлений
    """
    try:
        enabled = enabled_data.get("enabled", False)
        async with aiosqlite.connect(DB_NAME) as db:
            await set_notifications_enabled(db, enabled)
            await commit_changes(db)
            return {"message": f"Уведомления {'включены' if enabled else 'выключены'}"}
    except Exception as e:
        logger.error(f"Ошибка при установке статуса уведомлений: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.post("/api/v1/cartridges")
async def api_create_cartridge(payload: CartridgeCreateRequest, request: Request):
    """
    Создает новый картридж с штрих-кодом
    """
    db = request.app.state.db
    
    # Валидация входных данных
    if not payload.cartridge_name or not payload.cartridge_name.strip():
        raise HTTPException(status_code=400, detail="Название картриджа не может быть пустым")
    
    # Проверка штрих-кода
    if not payload.barcode or not payload.barcode.isdigit() or len(payload.barcode) != 13:
        raise HTTPException(status_code=400, detail="Штрих-код должен состоять из 13 цифр")
    
    # Проверка минимума
    if payload.min_qty < 1:
        raise HTTPException(status_code=400, detail="Минимальный остаток должен быть не менее 1")
    
    if payload.quantity_reserve < 0:
        raise HTTPException(status_code=400, detail="Резервное количество не может быть отрицательным")
    
    # Проверка на дубль штрих-кода
    if await barcode_exists(db, payload.barcode):
        raise HTTPException(status_code=409, detail="Штрих-код уже существует в базе")
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Получаем имя пользователя из сессии
    session_id = request.cookies.get("session_id")
    username = None
    if session_id:
        session_data = await get_session(db, session_id)
        if session_data:
            user_dn = session_data[0]
            # Извлекаем имя пользователя из DN (например, "cn=username" -> "username")
            if "cn=" in user_dn:
                username = user_dn.split("cn=")[1].split(",")[0]
            else:
                username = user_dn
    
    try:
        # Создаем картридж и добавляем первый штрих-код
        cartridge_id = await create_cartridge(
            db,
            payload.cartridge_name.strip(),
            max(0, payload.quantity),
            payload.min_qty,
            payload.quantity_reserve,
            payload.barcode,
            current_time
        )
        
        # Записываем в историю (операция добавления - delta = quantity)
        client_host = request.client.host
        user_agent = request.headers.get("User-Agent")
        os_info = "Platform: Windows       " if "Windows" in user_agent else "Platform: Mobile/Other  "
        client_info = os_info + client_host
        
        if max(0, payload.quantity) > 0:
            await add_history_record(
                db,
                cartridge_id,
                payload.cartridge_name.strip(),
                max(0, payload.quantity),
                client_info,
                current_time,
                username
            )
        
        await commit_changes(db)
        
        logger.info(f"{client_host} - 'Создан картридж ID: {cartridge_id} | Имя: {payload.cartridge_name} | Кол-во: {max(0, payload.quantity)} | Резерв: {payload.quantity_reserve}'")
        
        return {
            "id": cartridge_id,
            "message": "Картридж успешно создан"
        }
    
    except Exception as e:
        logger.error(f"Ошибка при создании картриджа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.delete("/api/v1/cartridges/{cartridge_id}")
async def api_delete_cartridge(cartridge_id: int, request: Request):
    """
    Удаляет картридж и все его штрих-коды из БД
    История операций остается нетронутой
    """
    db = request.app.state.db
    
    # Проверяем, существует ли картридж
    cartridge = await get_cartridge_by_id(db, cartridge_id)
    if not cartridge:
        raise HTTPException(status_code=404, detail="Картридж не найден")
    
    # Получаем имя картриджа перед удалением для логирования
    cartridge_name = await get_cartridge_name(db, cartridge_id)
    
    try:
        # Удаляем картридж и штрих-коды
        success = await delete_cartridge(db, cartridge_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Картридж не найден")
        
        await commit_changes(db)
        
        client_host = request.client.host
        logger.info(f"{client_host} - 'Удален картридж ID: {cartridge_id} | Имя: {cartridge_name}'")
        
        return {"message": "Картридж успешно удален"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении картриджа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# Перенаправление пользователя на файл админки    
@app.get("/")
async def redirect():
    return RedirectResponse(url='/admin-ui/pages/')

# Перенаправление пользователя на файл админки
@app.get("/admin-ui")
async def redirect():
    return RedirectResponse(url='/admin-ui/pages/')