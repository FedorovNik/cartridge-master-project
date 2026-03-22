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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cartridge_id) REFERENCES cartridges(id)
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
                             cartridge_name: str, delta: int, editor: str, timestamp: str):
    """
    Добавляет запись в историю изменений
    
    Args:
        db: Подключение к БД
        cartridge_id: ID картриджа
        cartridge_name: Название картриджа
        delta: Изменение количества (положительное или отрицательное)
        editor: Информация о редакторе (IP, платформа, и т.д.)
        timestamp: Время записи
    Returns:
        Ничего не возвращает, выполняет операцию с базой
    """
    await db.execute(
        """
        INSERT INTO history (cartridge_id, cartridge_name, delta, editor, created_at) 
        VALUES (?, ?, ?, ?, ?)
        """, 
        (cartridge_id, cartridge_name, delta, editor, timestamp)
    )

async def commit_changes(db: aiosqlite.Connection):
    """
    Сохраняет все изменения в БД
    
    Args:
        db: Подключение к БД
    Returns:
        Ничего не возвращает, комитит изменение в базе
    """
    await db.commit()
