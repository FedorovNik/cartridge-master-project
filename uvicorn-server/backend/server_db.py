"""
Модуль для управления логикой работы с базой данных
Содержит функции для инициализации БД, запросов и операций с данными
"""

import aiosqlite
import logging
from config import DB_NAME

logger = logging.getLogger("my_custom_logger")


################################### Инициализация таблиц БД ########################################################
async def init_database(db_connection):
    """
    Инициализирует подключение к БД и создает таблицы, если они не существуют
    
    Args:
        db_connection: aiosqlite объект подключения
    """
    try:
        # WAL для конкурентного доступа
        await db_connection.execute("PRAGMA journal_mode=WAL;")
        
        # Таблица картриджей
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS cartridges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cartridge_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 0,
                min_qty INTEGER DEFAULT 0,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица штрихкодов
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS barcodes (
                barcode TEXT PRIMARY KEY,
                cartridge_id INTEGER NOT NULL,
                FOREIGN KEY (cartridge_id) REFERENCES cartridges(id)
            )
        """)
        
        # Таблица истории изменений
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS history (
                increment INTEGER PRIMARY KEY AUTOINCREMENT,
                cartridge_id INTEGER NOT NULL,
                cartridge_name TEXT NOT NULL,
                delta INTEGER NOT NULL,
                editor TEXT NOT NULL,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cartridge_id) REFERENCES cartridges(id)
            )
        """)
        
        # Добавляем колонку username если её еще нет (для существующих БД)
        try:
            await db_connection.execute("ALTER TABLE history ADD COLUMN username TEXT")
        except:
            pass  # Колонка уже существует
        
        # Таблица сессий
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_dn TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        
        # Таблица email адресов для уведомлений
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_address TEXT NOT NULL UNIQUE,
                notifications_on BOOLEAN DEFAULT 0
            )
        """)
        
        # Таблица настроек
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        await db_connection.commit()
        logger.info("База данных проинициализирована.")
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise

################################### Функции для работы с базой ###################################################
async def get_cartridge_by_barcode(db: aiosqlite.Connection, barcode: str):
    """
    Получает ID картриджа по штрихкоду
    
    Args:
        db: Подключение к БД
        barcode: Штрихкод для поиска
        
    Returns:
        Кортеж (cartridge_id,) или None если не найден
    """
    cursor = await db.execute("SELECT cartridge_id FROM barcodes WHERE barcode = ?", (barcode,))
    return await cursor.fetchone()


async def get_cartridge_name_and_quantity(db: aiosqlite.Connection, cartridge_id: int):
    """
    Получает название и количество картриджа по ID
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        
    Returns:
        Кортеж (cartridge_name, quantity) или None если не найден
    """
    cursor = await db.execute(
        "SELECT cartridge_name, quantity FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    )
    return await cursor.fetchone()


async def get_cartridge_name(db: aiosqlite.Connection, cartridge_id: int):
    """
    Получает название картриджа по его ID
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        
    Returns:
        Имя картриджа или None если не найден
    """
    cursor = await db.execute(
        "SELECT cartridge_name FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def update_cartridge_quantity_add(db: aiosqlite.Connection, cartridge_id: int):
    """
    Увеличивает количество картриджа на 1
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
    """
    await db.execute(
        "UPDATE cartridges SET quantity = quantity + 1 WHERE id = ?", 
        (cartridge_id,)
    )


async def update_cartridge_quantity_subtract(db: aiosqlite.Connection, cartridge_id: int):
    """
    Уменьшает количество картриджа на 1 (если остаток > 0)
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        
    Returns:
        Объект cursor для проверки rowcount (количество затронутых строк)
    """
    cursor = await db.execute(
        "UPDATE cartridges SET quantity = quantity - 1 WHERE id = ? AND quantity > 0", 
        (cartridge_id,)
    )
    return cursor


async def get_all_cartridges(db: aiosqlite.Connection):
    """
    Получает всю информацию из базы по всем картриджам
    
    Args:
        db: Подключение к БД
        
    Returns:
        Список из словарей, в каждом словаре данные в JSON формате
    """
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
    # Возвращаем список из словарей (JSON)
    return [
        {
            "id": r[0],
            "name": r[1],
            "quantity": r[2],
            "min_qty": r[3],
            "last_update": r[4],
            "barcodes": r[5].split(",") if r[5] else []
        } for r in rows
    ]


async def get_cartridge_quantity(db: aiosqlite.Connection, cartridge_id: int):
    """
    Получает текущее количество картриджа
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        
    Returns:
        Количество картриджа (quantity) или None
    """
    async with db.execute(
        "SELECT quantity FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_cartridge_by_id(db: aiosqlite.Connection, cartridge_id: int):
    """
    Проверяет существование картриджа по его ID

    Возвращает кортеж (id,) или None
    """
    cursor = await db.execute(
        "SELECT id FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    )
    return await cursor.fetchone()


async def get_cartridge_stock_and_min(db: aiosqlite.Connection, cartridge_id: int):
    """
    Получает quantity и min_qty для картриджа по ID
    """
    cursor = await db.execute(
        "SELECT quantity, min_qty FROM cartridges WHERE id = ?", 
        (cartridge_id,)
    )
    return await cursor.fetchone()


async def update_cartridge_details(db: aiosqlite.Connection, cartridge_id: int, new_stock: int, new_min: int, new_name: str, timestamp: str):
    """
    Обновляет карточку картриджа по всем полям, используемым в API PATCH
    """
    await db.execute(
        "UPDATE cartridges SET quantity = ?, min_qty = ?, cartridge_name = ?, last_update = ? WHERE id = ?",
        (new_stock, new_min, new_name, timestamp, cartridge_id)
    )


async def barcode_exists(db: aiosqlite.Connection, barcode: str):
    cursor = await db.execute("SELECT 1 FROM barcodes WHERE barcode = ?", (barcode,))
    return (await cursor.fetchone()) is not None


async def add_barcode(db: aiosqlite.Connection, barcode: str, cartridge_id: int):
    await db.execute("INSERT INTO barcodes (barcode, cartridge_id) VALUES (?, ?)", (barcode, cartridge_id))


async def remove_barcode(db: aiosqlite.Connection, barcode: str, cartridge_id: int):
    cursor = await db.execute("DELETE FROM barcodes WHERE barcode = ? AND cartridge_id = ?", (barcode, cartridge_id))
    return cursor.rowcount


async def update_cartridge_quantity(db: aiosqlite.Connection, cartridge_id: int, new_quantity: int, timestamp: str):
    """
    Обновляет количество и время обновления картриджа
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        new_quantity: Новое количество
        timestamp: Новое время обновления
    Returns:
        Ничего не возвращает, выполняет операцию с базой
    """
    await db.execute(
        "UPDATE cartridges SET quantity = ?, last_update = ? WHERE id = ?", 
        (new_quantity, timestamp, cartridge_id)
    )


async def add_history_record(db: aiosqlite.Connection, cartridge_id: int, 
                             cartridge_name: str, delta: int, editor: str, timestamp: str, username: str = None):
    """
    Добавляет запись в историю изменений
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        cartridge_name: Название картриджа
        delta: Изменение количества (положительное или отрицательное)
        editor: Информация о редакторе (IP, платформа, и т.д.)
        timestamp: Время записи
        username: Имя пользователя (опционально, для операций от пользователя через веб)
    Returns:
        Ничего не возвращает, выполняет операцию с базой
    """
    await db.execute(
        """
        INSERT INTO history (cartridge_id, cartridge_name, delta, editor, username, created_at) 
        VALUES (?, ?, ?, ?, ?, ?)
        """, 
        (cartridge_id, cartridge_name, delta, editor, username, timestamp)
    )


async def get_yearly_expense_heatmap(db: aiosqlite.Connection, year: int):
    """
    Собирает данные для тепловой карты расходов по картриджам за выбранный год.
    Учитываются только отрицательные значения delta из таблицы history.

    Args:
        db: Подключение к БД
        year: Год, за который нужно построить тепловую карту

    Returns:
        Словарь с полями:
        - series: список серий для ApexCharts heatmap
        - available_years: годы, для которых уже есть данные списаний
    """
    month_labels = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]

    years_cursor = await db.execute(
        """
        SELECT DISTINCT CAST(strftime('%Y', created_at) AS INTEGER) AS year_value
        FROM history
        WHERE delta < 0 AND created_at IS NOT NULL
        ORDER BY year_value DESC
        """
    )
    year_rows = await years_cursor.fetchall()
    available_years = [row[0] for row in year_rows if row[0] is not None]

    cursor = await db.execute(
        """
        SELECT cartridge_name,
               CAST(strftime('%m', created_at) AS INTEGER) AS month_value,
               SUM(ABS(delta)) AS total_spent
        FROM history
        WHERE delta < 0
          AND created_at IS NOT NULL
          AND strftime('%Y', created_at) = ?
        GROUP BY cartridge_id, cartridge_name, month_value
        ORDER BY cartridge_name COLLATE NOCASE ASC, month_value ASC
        """,
        (str(year),)
    )
    rows = await cursor.fetchall()

    grouped = {}
    for cartridge_name, month_value, total_spent in rows:
        if cartridge_name not in grouped:
            grouped[cartridge_name] = [0] * 12

        if month_value and 1 <= month_value <= 12:
            grouped[cartridge_name][month_value - 1] = total_spent

    series = []
    for cartridge_name, monthly_values in grouped.items():
        series.append({
            "name": cartridge_name,
            "data": [
                {"x": month_labels[index], "y": monthly_values[index]}
                for index in range(12)
            ]
        })

    return {
        "series": series,
        "available_years": available_years
    }


async def commit_changes(db: aiosqlite.Connection):
    """
    Сохраняет все изменения в БД
    
    Args:
        db: Подключение к БД
    Returns:
        Ничего не возвращает, комитит изменение в базе
    """
    await db.commit()


################################### Функции для работы с сессиями ###################################################

import uuid
from datetime import datetime, timedelta

async def create_session(db: aiosqlite.Connection, user_dn: str) -> str:
    """
    Создает новую сессию для пользователя
    
    Args:
        db: Подключение к БД
        user_dn: DN пользователя
        
    Returns:
        session_id: Уникальный ID сессии
    """
    session_id = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=7)  # Сессия на 7 дней
    
    await db.execute(
        "INSERT INTO sessions (session_id, user_dn, expires_at) VALUES (?, ?, ?)",
        (session_id, user_dn, expires_at.isoformat())
    )
    await db.commit()
    return session_id


async def get_session(db: aiosqlite.Connection, session_id: str):
    """
    Получает информацию о сессии
    
    Args:
        db: Подключение к БД
        session_id: ID сессии
        
    Returns:
        Кортеж (user_dn, expires_at) или None если сессия не найдена или истекла
    """
    cursor = await db.execute(
        "SELECT user_dn, expires_at FROM sessions WHERE session_id = ?",
        (session_id,)
    )
    row = await cursor.fetchone()
    if row:
        user_dn, expires_at_str = row
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now() < expires_at:
            return user_dn, expires_at
    return None


async def delete_session(db: aiosqlite.Connection, session_id: str):
    """
    Удаляет сессию
    
    Args:
        db: Подключение к БД
        session_id: ID сессии
    """
    await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    await db.commit()


async def cleanup_expired_sessions(db: aiosqlite.Connection):
    """
    Удаляет истекшие сессии
    
    Args:
        db: Подключение к БД
    """
    await db.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now().isoformat(),))
    await db.commit()


################################### Функции для работы с email уведомлениями ###################################################

async def get_all_emails(db: aiosqlite.Connection):
    """
    Получает все email адреса из базы
    
    Args:
        db: Подключение к БД
        
    Returns:
        Список словарей с email данными
    """
    cursor = await db.execute("SELECT id, email_address, notifications_on FROM emails ORDER BY email_address")
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "email_address": r[1],
            "notifications_on": bool(r[2])
        }
        for r in rows
    ]


async def add_email(db: aiosqlite.Connection, email_address: str):
    """
    Добавляет новый email адрес
    
    Args:
        db: Подключение к БД
        email_address: Email адрес для добавления
        
    Returns:
        ID нового email или None если ошибка
    """
    try:
        cursor = await db.execute("INSERT INTO emails (email_address) VALUES (?)", (email_address,))
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        return None  # Email уже существует


async def update_email_notifications(db: aiosqlite.Connection, email_id: int, notifications_on: bool):
    """
    Обновляет статус уведомлений для email
    
    Args:
        db: Подключение к БД
        email_id: ID email
        notifications_on: Включены ли уведомления
    """
    await db.execute("UPDATE emails SET notifications_on = ? WHERE id = ?", (int(notifications_on), email_id))


async def delete_email(db: aiosqlite.Connection, email_id: int):
    """
    Удаляет email адрес
    
    Args:
        db: Подключение к БД
        email_id: ID email для удаления
        
    Returns:
        Количество удаленных строк
    """
    cursor = await db.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    return cursor.rowcount


async def get_emails_for_notifications(db: aiosqlite.Connection):
    """
    Получает список email адресов, для которых включены уведомления
    
    Args:
        db: Подключение к БД
        
    Returns:
        Список email адресов
    """
    cursor = await db.execute("SELECT email_address FROM emails WHERE notifications_on = 1")
    rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def get_low_stock_cartridges(db: aiosqlite.Connection):
    """
    Получает картриджи с низким запасом (quantity <= min_qty)
    
    Args:
        db: Подключение к БД
        
    Returns:
        Список словарей с данными картриджей
    """
    cursor = await db.execute("""
        SELECT id, cartridge_name, quantity, min_qty 
        FROM cartridges 
        WHERE quantity <= min_qty 
        ORDER BY cartridge_name
    """)
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "quantity": r[2],
            "min_qty": r[3]
        }
        for r in rows
    ]


################################### Функции для работы с настройками ###################################################

async def get_setting(db: aiosqlite.Connection, key: str, default_value: str = ""):
    """
    Получает значение настройки
    
    Args:
        db: Подключение к БД
        key: Ключ настройки
        default_value: Значение по умолчанию
        
    Returns:
        Значение настройки или default_value
    """
    cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    return row[0] if row else default_value


async def set_setting(db: aiosqlite.Connection, key: str, value: str):
    """
    Устанавливает значение настройки
    
    Args:
        db: Подключение к БД
        key: Ключ настройки
        value: Значение настройки
    """
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )


async def get_notification_schedule(db: aiosqlite.Connection):
    """
    Получает расписание отправки уведомлений
    
    Args:
        db: Подключение к БД
        
    Returns:
        Словарь с полями: days_of_week (строка с днями через запятую), time_hm (ЧЧ:ММ) или None если не установлено
    """
    days_cursor = await db.execute("SELECT value FROM settings WHERE key = 'notification_days'")
    days_row = await days_cursor.fetchone()
    
    time_cursor = await db.execute("SELECT value FROM settings WHERE key = 'notification_time'")
    time_row = await time_cursor.fetchone()
    
    if not days_row or not time_row:
        return None
    
    return {
        "days_of_week": days_row[0],
        "time_hm": time_row[0]
    }


async def set_notification_schedule(db: aiosqlite.Connection, days_of_week: str, time_hm: str):
    """
    Устанавливает расписание отправки уведомлений
    
    Args:
        db: Подключение к БД
        days_of_week: Строка с днями недели через запятую (0-6)
        time_hm: Время в формате ЧЧ:ММ
    """
    import re
    # Проверка формата времени
    if not re.match(r"^\d{2}:\d{2}$", time_hm):
        raise ValueError("Неверный формат времени. Используйте ЧЧ:ММ")
    
    # Проверка дней недели
    if not days_of_week or days_of_week.strip() == '':
        raise ValueError("Необходимо выбрать хотя бы один день недели")
    
    days = days_of_week.split(',')
    for day_str in days:
        day = int(day_str.strip())
        if not (0 <= day <= 6):
            raise ValueError("День недели должен быть от 0 до 6")
    
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("notification_days", days_of_week)
    )
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("notification_time", time_hm)
    )


async def get_notifications_enabled(db: aiosqlite.Connection) -> bool:
    """
    Получает статус глобальной настройки уведомлений
    
    Args:
        db: Подключение к БД
        
    Returns:
        True если уведомления включены, False иначе
    """
    cursor = await db.execute("SELECT value FROM settings WHERE key = 'notifications_enabled'")
    row = await cursor.fetchone()
    
    if row:
        return row[0].lower() == 'true'
    
    return False  # По умолчанию выключено


async def set_notifications_enabled(db: aiosqlite.Connection, enabled: bool):
    """
    Устанавливает статус глобальной настройки уведомлений
    
    Args:
        db: Подключение к БД
        enabled: True для включения, False для выключения
    """
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("notifications_enabled", str(enabled))
    )


################################### Функции для создания и удаления картриджей ###################################################

async def create_cartridge(db: aiosqlite.Connection, cartridge_name: str, quantity: int, 
                          min_qty: int, barcode: str, timestamp: str) -> int:
    """
    Создает новый картридж и добавляет первый штрих-код
    
    Args:
        db: Подключение к БД
        cartridge_name: Название картриджа
        quantity: Начальное количество
        min_qty: Минимальный остаток
        barcode: Первый штрих-код (обязателен)
        timestamp: Время создания
        
    Returns:
        ID нового картриджа
    """
    cursor = await db.execute(
        """
        INSERT INTO cartridges (cartridge_name, quantity, min_qty, last_update) 
        VALUES (?, ?, ?, ?)
        """,
        (cartridge_name, quantity, min_qty, timestamp)
    )
    cartridge_id = cursor.lastrowid
    
    # Добавляем первый штрих-код
    await db.execute(
        "INSERT INTO barcodes (barcode, cartridge_id) VALUES (?, ?)",
        (barcode, cartridge_id)
    )
    
    return cartridge_id


async def delete_cartridge(db: aiosqlite.Connection, cartridge_id: int) -> bool:
    """
    Удаляет картридж и все связанные штрих-коды
    История операций с картриджем остается в таблице history
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа для удаления
        
    Returns:
        True если картридж был удален, False если не найден
    """
    # Проверяем существование картриджа
    result = await get_cartridge_by_id(db, cartridge_id)
    if not result:
        return False
    
    # Удаляем все штрих-коды
    await db.execute("DELETE FROM barcodes WHERE cartridge_id = ?", (cartridge_id,))
    
    # Удаляем сам картридж
    await db.execute("DELETE FROM cartridges WHERE id = ?", (cartridge_id,))
    
    return True
