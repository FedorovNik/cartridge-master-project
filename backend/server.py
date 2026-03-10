from fastapi import FastAPI, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import logging
import sys
import uvicorn
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


# Создаем базовый логгер
logger = logging.getLogger("my_custom_logger")
logger.setLevel(logging.INFO)

# Используем DefaultFormatter как в uvicorn
formatter = DefaultFormatter("%(levelprefix)s %(message)s")

# Настраиваем вывод в консоль
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)



hostname: str = socket.gethostname()
local_ip: str = socket.gethostbyname(hostname)

logger.info(f"IP-адрес: {local_ip}")
logger.info(f"Имя хоста: {hostname}")




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

@asynccontextmanager
async def lifespan(app: FastAPI):

    async with aiosqlite.connect(DB_NAME) as db:
        # Картриджи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cartridges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cartridge_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 0,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                increment INTEGER PRIMARY KEY AUTOINCREMENT,
                cartridge_id INTEGER NOT NULL,
                cartridge_name INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                editor TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cartridge_id) REFERENCES cartridges(id)
            )
        """)
        logger.info(f"БД SQLite проинициализована или уже существует.")
        await db.commit()


    # Запуск при старте функции очистки сета айдишников транзакций ТСД
    asyncio.create_task(clean_ids_task())
    yield
    # При остановке можно добавить логику здесь

app = FastAPI(lifespan=lifespan)


# Монтажим папку с фронтом как /admin-ui
app.mount("/admin-ui", StaticFiles(directory="frontend", html=True), name="admin-ui")
AES_KEY = "My_Secret_Key_16"
DB_NAME = "inventory.db"

# В FastApi нужен класс для описания структуры входящих данных.
# ТСД отправляет зашифрованный в base64 plain text, который после расшифровки представляет из себя json-структуру.
# Поэтому нужно описать класс, который ожидает строку (payload).
class ScanRequest(BaseModel):
    payload: str

# Дешифратор для запросов от ТСД
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
    cipher = AES.new(AES_KEY.encode('utf-8'), AES.MODE_CBC) # IV сгенерируется сам
    ct_bytes = cipher.encrypt(pad(data_str.encode('utf-8'), AES.block_size))
    combined = cipher.iv + ct_bytes
    return base64.b64encode(combined).decode('utf-8')

# Джокушка локера от любопытных глаз
@app.get("/scan")
async def trap_page():
    # Мы используем CSS, чтобы растянуть картинку на весь экран
    # и добавить красный фон для драматизма
    # и вообще убрать нафиг в папку фронта
    html_content = """
    <html>
        <head>
            <title>Вы кто такие?</title>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    background-color: #1a0000;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    overflow: hidden;
                }
                img {
                    max-width: 90%;
                    max-height: 90%;
                    border: 10px solid black; 
                    box-shadow: 0 0 50px rgba(255, 0, 0, 0.4);
                }
            </style>
        </head>
        <body>
            <img src="admin-ui/static/403.png" alt="403 Forbidden - Вы кто такие?">
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

#  Эндпоинт для ТСД 
@app.post("/scan")
# Указывает объект класса ScanRequest, который будет автоматически заполняться данными из тела запроса.
async def process_scan(data: ScanRequest):
    # Отправляем в дешифратор абракадабру, которая должна быть расшифрована в JSON-строки
    decrypted_json_str = decrypt_payload(data.payload)
    
    if not decrypted_json_str:
        return PlainTextResponse(
            encrypt_payload("Ошибка: AES-Ключ не совпадал на сервере или пакет поврежден!"),
            status_code=status.HTTP_400_BAD_REQUEST
        )

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

        
        async with aiosqlite.connect(DB_NAME) as db:
            # Ищем штрихкод
            cursor = await db.execute("SELECT cartridge_id FROM barcodes WHERE barcode = ?", (req_barcode,))
            row = await cursor.fetchone()
            
            if not row:
                # Устанавливаем код 404 (Not Found)
                msg = f"Штрихкод {req_barcode} не привязан!"
                return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_404_NOT_FOUND)

            # Нашли id по этому штрихкоду
            cartridge_id = row[0]

            # Обновляем количество +1 в таблице cartridges
            if req_action == 'add':
                await db.execute("UPDATE cartridges SET stock = stock + 1 WHERE id = ?", (cartridge_id,))

            # Обновляем количество -1 в таблице cartridges
            else:
                cursor = await db.execute("UPDATE cartridges SET stock = stock - 1 WHERE id = ? AND stock > 0", (cartridge_id,))
                if cursor.rowcount == 0:
                    # rowcount - счетчик измененных строк
                    
                    msg = "Ошибка: Остаток не может быть меньше нуля!"
                    return PlainTextResponse(encrypt_payload(msg), status_code=status.HTTP_409_CONFLICT)
                
            await db.commit()
            # Получаем новый остаток для ответа
            cursor = await db.execute("SELECT name, stock FROM cartridges WHERE id = ?", (cartridge_id,))
            name, new_stock = await cursor.fetchone()

        # Шифро-ответ ТСД: запрос обработан
        return PlainTextResponse(encrypt_payload(f"Имя: {name}\nШтрих-код:{req_barcode}\nОстаток: {new_stock}"))

        
    except Exception as e:
        # Шифро-ответ ТСД: непонятный косяк на сервере
        return PlainTextResponse(encrypt_payload("Непредвиденная критическая ошибка сервера!"), status_code=500)


# ЧИСТЫЙ API ДЛЯ АДМИНКИ (JSON) 
@app.get("/api/v1/cartridges")
async def get_inventory():
    async with aiosqlite.connect(DB_NAME) as db:
        # Магия SQL: получаем имя, список штрихкодов через запятую и сумму остатков
        cursor = await db.execute("""
            SELECT 
                c.id, 
                c.cartridge_name,
                c.quantity, 
                GROUP_CONCAT(DISTINCT b.barcode) as barcodes
            FROM cartridges c
            LEFT JOIN barcodes b ON c.id = b.cartridge_id
            GROUP BY c.id
        """)
        rows = await cursor.fetchall()
        
        return [
            {
                "id": r[0],
                "name": r[1],
                "stock": r[2],
                "barcodes": r[3].split(",") if r[3] else []
                
            } for r in rows
        ]
@app.get("/")
async def root_redirect():
    # Перенаправляем пользователя сразу на файл админки
    return RedirectResponse(url='/admin-ui/')
@app.get("/admin-ui")
async def root_redirect():
    # Перенаправляем пользователя сразу на файл админки
    return RedirectResponse(url='/admin-ui/')

if __name__ == "__main__":
    
    logger.info(f"Выполняется запуск uvicorn-процесса...")
    # Uvicorn слушает только запросы с сервера, на котором он запущен.
    # Сделано так, для того, чтобы нельзя было попаcть на него "в обход"
    # прокси caddy из локалки по http и 8080 порту
    uvicorn.run(app, host="127.0.0.1", port=8080)