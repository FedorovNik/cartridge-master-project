
from sqlite3 import Row
from sqlite3 import Row
from sqlite3 import Row
from sqlite3 import Row
from aiogram import Bot, Router, F
from aiogram.filters import Command, BaseFilter, CommandObject
from aiogram.methods.send_message import SendMessage
from aiogram.types import Message
import re


import platform
from importlib.metadata import version
from app.database.db_operations import add_user, get_all_users, user_exists, del_user,\
                                       get_all_cartridges, get_tg_id_list_notification,\
                                       get_cartridge_by_name, update_cartridge_count, update_user_notice,\
                                       get_cartridge_by_barcode, insert_new_cartridge, get_cartridge_by_id, \
                                       delete_cartridge, insert_new_barcode,delete_barcode
import logging

import socket
hostname: str = socket.gethostname()
local_ip: str = socket.gethostbyname(hostname)


logger: logging.Logger = logging.getLogger(__name__)

def is_number(s) -> bool:
    try:
        # Если преобразуется в float без ошибок, значит это число (может быть целым или с плавающей точкой)
        float(s) 
        return True
    except ValueError:
        return False

# Объект роутера класса Роутер 
rt = Router()

# Базовый фильтр для проверки авторизованного пользователя
class AuthorizedFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # Вызываем метод базы и закидываем в него только ИД отправителя сообщения,
        # полученный из объекта message. Любой бред полученный от рандомов будет пропускаться
        # (защита от инъекций), но к сожалению всё равно будет дергаться база при
        # каждом сообщении, иначе хз как сделать. 
        return await user_exists(message.from_user.id)

# Применяем его ко всем сообщениям в роутере
rt.message.filter(AuthorizedFilter())

@rt.message(Command("start"))
async def start(message: Message) -> None:
    
    python_ver: str = platform.python_version()
    aiogram_ver: str = version("aiogram")
    aiohttp_ver: str = version("aiohttp")
    aiosqlite_ver: str = version("aiosqlite")
    await message.answer(f"<b>Привет, {message.from_user.first_name}!</b>"
                        f"\nБот работает на асинхронном python фреймворке для ТГ-ботов <code>aiogram</code>."
                        f" Требуемые зависимости представлены списком в <code>requirements.txt</code> в корне."
                        f" База данных SQLite с картриджами, пользователями и историей расходов хранится в файле <code>database.db</code>,"
                        f" коротый находится в той же директории с программой."
                        f"\nЛюбое сообщение, отправленное боту проверяется - находится ли отправитель в базе (таблице users)."
                        f" Бот отвечает только людям, которые находятся в этой локальной базе."
                        f"\n\nПрограмма логически разделена на 2 модуля - директории <b>bot</b> и <b>web</b>."
                        f"\nБот и веб-сервер работают в 1 процессе и 1 потоке, с помощью кооперативной многозадачности,"
                        f" которую обеспечивает асинхронная библиотека <code>asyncio</code>."
                        f"\n1. Диспетчер бота регистрирует и обрабатывает все события, получаемые от серверов телеграма."
                        f"\n2. HTTP-сервер принимает и обрабатывает POST-запросы от ТСД по адресу http://{local_ip}:8080/scan.\
                            \nТрафик между ТСД и веб-сервером передается в зашифрованном виде (алгоритм AES).\
                            \nКлюч шифрования AES_KEY зашит в коде на серверной части и ТСД-шнике."
                        f"\n\n<b>Краткая основная информация о версиях:</b>"
                        f"\nPython:  <code>{python_ver}</code>."
                        f"\nAiogram: <code>{aiogram_ver}</code>"
                        f"\nAiohttp: <code>{aiohttp_ver}</code>"
                        f"\nAiosqlite: <code>{aiosqlite_ver}</code>"
                        f"\n\nДля получения справки по командам бота вызови <b>/help</b>\n"
                        ,parse_mode="HTML"
    )

@rt.message(Command("help"))
async def help(message: Message) -> None:
    await message.answer(
    f"<b>Работа с таблицей картриджей:\n</b>"
    f"<b>/list</b>\nВывести всю инфу по картриджам.\n"
    f"<b>/updatecount</b>\nОбновить количество определенного картриджа.\n"
    f"<b>/addbar</b>\nДобавить штрих-код для определенного картриджа.\n"
    f"<b>/delbar</b>\nУдалить штрих-код для определенного картриджа.\n"
    f"<b>/insert</b>\nДобавить новый картридж, отсутствующий в таблице.\n"
    f"<b>/delete</b>\nУдалить запись о картридже из таблицы.\n\n"

    f"<b>Работа с таблицей пользователей:\n</b>"
    f"<b>/users</b>\nВывести список всех пользователей.\n"
    f"<b>/adduser</b>\nДобавить нового пользователя в таблицу.\n"
    f"<b>/deluser</b>\nУдалить пользователя из таблицы.\n"
    f"<b>/notice</b>\nВключение/отключение уведомлений пользователям в личку от ТСД.\n"
    ,parse_mode="HTML"
    )

@rt.message(Command("adduser"))
async def adduser(message: Message, command: CommandObject) -> Message | None:
    # Проверяем, что аргументы вообще есть
    if not command.args:
        return await message.answer("Команда добавления пользователя в базу требует аргументов:"
                                    "\n<b>/adduser TG_ID USER_NAME</b>\n"
                                    "\n\nTG_ID: уникальный телеграм идентификатор пользователя"
                                    "\nUSER_NAME: имя пользователя в локальной базе",
                                    parse_mode="HTML")
    
    # Проверка кол-ва аргументов, ожидается только ID и NAME
    parts: list[str] = command.args.split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer("Неверное количество аргументво команды!")
    user_id_str, user_name = parts

    # Проверка на число
    if not user_id_str.isdigit():
        return await message.answer("ID должен состоять только из цифр!")

    # Если все ок пишем в базу
    await add_user(
        telegram_id=int(user_id_str),
        first_name=user_name
    )
    
    await message.answer(f"Пользователь <b>{user_name}</b> с ID: <b>{user_id_str}</b> добавлен.", parse_mode="HTML")

@rt.message(Command("deluser"))
async def deluser(message: Message, command: CommandObject) -> Message | None:
    # Проверяем, что аргументы вообще есть
    if not command.args:
        return await message.answer("Команда удаления пользователя из базы требует аргументов:"
                                    "\n<b>/deluser TG_ID</b>"
                                    "\n\nTG_ID: уникальный телеграм идентификатор пользователя",
                                    parse_mode="HTML")
    
    # Проверка кол-ва аргументов, ожидается только один айдишник
    parts: list[str] = command.args.split(maxsplit=1)
    if len(parts) != 1:
        return await message.answer("Неверное количество аргументов команды!")
    # Единственный элемент списка заносим в переменную
    user_id_str: str = parts[0]

    # Проверка на число
    if not user_id_str.isdigit():
        return await message.answer("ID должен состоять только из цифр!")

    # Если все ок вызываем функцию базы, результат выполнения del_user сравниваем - удалился или нет
    result_del: bool = await del_user(telegram_id=int(user_id_str))
    if result_del > 0:
        await message.answer(f"Пользователь c ID: <b>{user_id_str}</b> удален.", parse_mode="HTML")
    else:
        await message.answer(f"Пользователя c ID: <b>{user_id_str}</b> нет в базе.", parse_mode="HTML")
    

@rt.message(Command("users"))
async def list_users(message: Message) -> None:
    users: logging.Iterable[Row] = await get_all_users()
    if not users:
        await message.answer("Список пользователей в базе пуст!")
        return

    text = "Список пользователей:\n\n"
    for user in users:
        text += f"Имя:  <b>{user[2]}</b>  -  ID: {user[1]} -  Уведомления: {user[3]}\n"
    await message.answer(text, parse_mode="HTML")

@rt.message(Command("list"))
async def list_cartridges(message: Message, command: CommandObject) -> None:
    # Получаем все картриджи из БД
    cartridges = await get_all_cartridges()
    
    if not cartridges:
        await message.answer("Склад пуст!\nКартриджи не найдены.", parse_mode="HTML")
        return

    # Анализ аргументов и регуляка
    search_pattern = None
    if command.args: # Если после /list есть текст
        try:
            # Компилируем регулярку игнорируя регистр
            search_pattern = re.compile(command.args, re.IGNORECASE)
        except re.error:
            await message.answer("Ошибка в синтаксисе регулярного выражения!", parse_mode="HTML")
            return

    # Настраиваем заголовок в зависимости от того, есть ли поиск
    if search_pattern:
        header = f"<b>Результаты поиска по:</b> <code>{command.args}</code>\n"
    else:
        header = "<b>Текущие остатки на складе:</b>\n"
    header += "<code>" + "—" * 33 + "</code>\n"
    
    text_lines = []
    
    for item in cartridges:
        id_val, cartridge_name, quantity, all_barcodes, last_update = item

        # ФИЛЬТРАЦИЯ ПО РЕГУЛЯРКЕ!!!!
        # Если есть паттерн поиска, и имя картриджа под него НЕ попадает — пропускаем итерацию
        if search_pattern and not search_pattern.search(str(cartridge_name)):
            continue

        status_color: str = ""
        if quantity >= 6:
            status_color = "✅ Норм!  "
        elif quantity >= 3:
            status_color = "⚠️ Средне!"
        elif quantity >= 0:
            status_color = "❌ Мало!  "
        else:
            logger.error(f"| TELEGRAM |   НЕДОПУСТИМО   | Отрицательное количество | ID: {id_val} Наименование: {cartridge_name} Количество: {quantity}")
            await message.answer(
                f"В базе отрицательное количество!\n"
                f"ID: {id_val}\n"
                f"Штрих-код: {all_barcodes}\n"
                f"Наименование: {cartridge_name}\n"
                f"Количество: {quantity}"
            )
            continue # Лучше пропустить этот проблемный пункт, но продолжить вывод остальных
        
        # Формируем блок для одного картриджа
        line = f"{status_color}      <b>{cartridge_name}</b>\n"
        line += f"Количество:   <b>{quantity}</b> шт.\n"

        if all_barcodes:
            barcodes_list = all_barcodes.split("; ")
            for barcode in barcodes_list:
                line += f"Штрих-код:     <b>{barcode}</b>\n"

        line += f"Изменение:    <b>{last_update}</b>\n"
        line += f"ID в базе:         <b>{id_val}</b>\n\n"
        
        text_lines.append(line)

    # Если после фильтрации ничего не осталось
    if not text_lines:
        await message.answer("По запросу ничего не найдено!", parse_mode="HTML")
        return

    # АДЕКВАТНАЯ РАЗБИВКА НА СООБЩЕНИЯ - замена старой хрени
    # Лимит телеги 4096 символов. Будем собирать сообщения кусками по 4000 символов,
    # чтобы  не обрезать HTML-теги на полуслове.
    messages_to_send = []
    current_msg = header
    
    for line in text_lines:
        # Если добавление следующего блока превысит лимит (запас в 96 символов)
        if len(current_msg) + len(line) > 4000:
            messages_to_send.append(current_msg)
            current_msg = line # Начинаем собирать новое сообщение с текущего блока
        else:
            current_msg += line
            
    # добавить последний собранный кусок
    if current_msg:
        messages_to_send.append(current_msg)

    # все собранные куски по очереди
    for msg in messages_to_send:
        await message.answer(msg, parse_mode="HTML")


@rt.message(Command("notice"))
async def notice(message: Message, command: CommandObject) -> Message | None:
    # Проверяем, что аргументы вообще есть
    if not command.args:
        return await message.answer("Команда включения уведомлений пользователям от ТСД требует аргументов."
                                    "\n\n<b>/notice TG_ID ON_OFF</b>"
                                    "\nПараметр ON_OFF принимает только булевые 0 и 1, отвечает за включение и отключение уведомлений."
                                    "\n\nПример синтаксиса для включения уведомлений:"
                                    "\n<b>/notice 123456789 1</b>",
                                    parse_mode="HTML")
    
    # Проверка кол-ва аргументов, ожидается только ID(цифровая) и BOOL(булевая)
    parts: list[str] = command.args.split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer("Неверное количество аргументво команды!")
    
    user_id_str, on_off_str = parts
    # Проверка на число
    if not user_id_str.isdigit():
        return await message.answer("ID должен состоять только из цифр!")
    # Проверка 
    if on_off_str not in ("0", "1"):
        return await message.answer("Параметр уведомлений может быть только 0 или 1!")
    
    # Проверяем есть ли вообще пользователь с таким ID в базе, если нет - выходим с сообщением, что такого пользователя нет.
    if await user_exists(user_id_str):
        await update_user_notice(
            telegram_id=int(user_id_str),
            notice_enabled=int(on_off_str),
        )
        await message.answer(f"Уведомления изменены на <b>{on_off_str}</b> \
                              \nПользователь с ID: <b>{user_id_str}</b>", parse_mode="HTML")
    else:
        return await message.answer(f"Пользователя с ID: {user_id_str} нет в базе!")


# Аналогичная функция по функционалу (как и в случае с ТСД) для обновления позиции количества картриджа в базе. 
# Надо потом как нибудь переделать покрасивее  
@rt.message(Command("updatecount"))
async def updatecount(message: Message, command: CommandObject, bot:Bot) -> Message | None:
    
    if not command.args:
        return await message.answer("Команда обновления количества картриджей в базе требует аргументов."
                                "\n<b>/updatecount ID CHANGE</b>"
                                "\n\n<b>ID</b>: принимает только уникальный ID картриджа. Посмотреть можно выведя список /list"
                                "\n<b>CHANGE</b>: принимает положительные и отрицательные значения от -15 до 15."
                                "Он определяет количество добавляемых картриджей в базу."
                                "\n\nПример добавления двух картриджей с ID 5:"
                                "\n/updatecount <b>5 +2</b>"
                                "\nПример удаления двух картриджей с ID 5:"
                                "\n/updatecount <b>5 -2</b>",
                                parse_mode="HTML")

    # Нам нужно только два аргумента
    parts: list[str] = command.args.split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer("Неверное количество аргументов команды!")
    cartridge_id, change = parts

    # Простые проверки аргументов
    if not cartridge_id.isdigit():
        return await message.answer("ID должен состоять только из цифр!")
    if not is_number(cartridge_id):
        return await message.answer("ID должно быть числом!")
    if int(cartridge_id) == 0:
        return await message.answer("ID=0 не может быть в базе!")
    
    if not is_number(change):
        return await message.answer("Количество должно быть числом!")
    if not(-15 <= int(change) <= 15):
        return await message.answer("Количество должно быть от -15 до 15!")
    if int(change) == 0:
        return await message.answer("Какой в этом смысл?")
    

    # Список айдишек для метода бота send_message
    user_ids = await get_tg_id_list_notification()

    # Заготовка текста для answer
    msg_text: str = f"  TG_ID: {message.from_user.id}        | Имя: {message.from_user.first_name}"

    # Получает кортеж по айдишнику
    cartridge_res = await get_cartridge_by_id(cartridge_id)
    if not(cartridge_res):
        return await message.answer(f"Такого ID нет в базе!")
    
    #!!!!!!! Когда переделаю функцию update_cartridge_count чтобы она принимала айдишник а не штрих, тут надо изменить!!!!!!!!
    # Берем 2 элемент(набор штрихкодов) из кортежа cartridge_res и делим по двоеточиям как отдельные элементы массива
    # Берем первый попавшийся, без разницы какой они все принадлежат одному картриджу.
    barcodes_list = cartridge_res[2].split("; ")

    # Вызываем функцию базы
    db_operation_res: tuple[int, str] | str = await update_cartridge_count(barcodes_list[0], int(change))
    
    # Обработка db_operation_res
    # Если вернулся кортеж из (new_qty, name)
    # Отправляем уведомление в тг ВСЕМ кто в рассылке и логируем как инфо
    if isinstance(db_operation_res, tuple) and len(db_operation_res) == 2:
        balance, cartridge_name = db_operation_res
        #logger.info(f"| TELEGRAM |   Обновлена БД  | Штрих-код: {barcode} | Имя: {cartridge_name} | Количество: {balance}")
        for user_id in user_ids:
            try:
                await bot.send_message(chat_id=user_id, 
                                       text=f"Операция выполнена.\
                                       \nИмя:                  <b>{cartridge_name}</b>\
                                       \nКоличество:   <b>{balance}</b>", parse_mode="HTML")
                
                logger.info(f"| TELEGRAM |    ДОСТАВЛЕНО   |" + msg_text)
            except Exception as e:
                logger.warning(f"| TELEGRAM |  НЕ ДОСТАВЛЕНО  |"+ msg_text)
                return None
            return
        
    # Обработка db_operation_res
    # Если вернулась строка: NOT_FOUND:BARCODE или NO_STOCK:CARTRIDGE_NAME
    # Отправляем ОТВЕТ в тг и логируем как предупреждение
    elif isinstance(db_operation_res, str):
        barcode_or_name: str = db_operation_res.split(":", 1)[1]
        
        # Если не найден картридж по штриху в базе отправляем в лог и в тг-ответ
        if db_operation_res.startswith("NOT_FOUND:"):
            #logger.warning(f"| TELEGRAM | Не обновлена БД | Не найден штрих-код: {barcode_or_name}")
            # Если не ушел ответ тоже логируем
            try:
                await message.answer(f"Операция не выполнена!\
                                     \nПричина:         <b>нет в базе</b>.\
                                     \nШтрих-код:     <b>{barcode_or_name}</b>",parse_mode="HTML")
            except Exception as e:
                logger.warning(f"| TELEGRAM | НЕ ДОСТАВЛЕНО | "+ msg_text)
                return None
            logger.info(f"| TELEGRAM |    ДОСТАВЛЕНО   |" + msg_text)
            return
        
        # Если не получилось изменить количество в базе отправляем в лог и в тг-ответ
        if db_operation_res.startswith("NO_STOCK:"):
            #logger.warning(f"| TELEGRAM | Не обновлена БД | Нет на складе или отрицательное количество: {barcode_or_name}")
            # Если не ушел ответ тоже логируем
            try:
                await message.answer(f"Операция не выполнена!\
                                     \nНаименование: {barcode_or_name} \
                                     \nПричина: нет на складе или \
                                     отрицательное количество после выполнения операции.\
                                    ")
            except Exception as e:
                logger.warning(f"| TELEGRAM | НЕ ДОСТАВЛЕНО | "+ msg_text)
                return None
            logger.info(f"| TELEGRAM |    ДОСТАВЛЕНО   | "+ msg_text)
            return

    # Любой другой вариант это косяк update_cartridge_count()  — возвращаем 400
    else:
        logger.error(f"| TELEGRAM |      ОШИБКА     | Вернула неожиданный результат: {db_operation_res}")
        for user_id in user_ids:
            return await bot.send_message(chat_id=user_id, text=f"Ошибка!\
                                                                \nНеожиданный ответ от БД.\
                                                                \nВернулось: {db_operation_res}")

# Хэндлер для вставки нового картриджа в базу.
@rt.message(Command("insert"))
async def insert(message: Message, command: CommandObject, bot:Bot) -> Message | None:
    
    if not command.args:
        return await message.answer("Команда добавления <b>нового</b> картриджа в таблицу.\n"
                                "<b>/insert BARCODE CARTRIDGE_NAME QUANTITY</b>\n"
                                "Параметр BARCODE принимает только штрих-код картриджа.\n"
                                "Параметр CARTRIDGE_NAME принимает строковое значение имени картриджа.\n"
                                "Имя НЕ ДОЛЖНО содержать пробелов, но ним дробятся аргументы.\n"
                                "Параметр QUANTITY принимает количество этого картриджа.\n\n"
                                "Пример синтаксиса для вставки в базу двух картриджей с именем new_cartridge:\n"
                                "<b>/insert 1234567891234 new_cartridge 2</b>\n",
                                parse_mode="HTML")

    # Нам нужно только 3 аргумента
    parts = command.args.split()
    if len(parts) != 3:
        return await message.answer("Неверное количество аргументов команды!")
    barcode, cartridge_name, quantity = parts

    # Проверки: имя проверять нет смысла, количество должно быть числом, штрих - строка состоящая из цифр
    if not barcode.isdigit():
        return await message.answer("Штрих-код должен состоять только из цифр!")
    if not is_number(quantity):
        return await message.answer("Количество должно быть числом!")
    if not(-15 <= int(quantity) <= 15):
        return await message.answer("Количество должно быть от -15 до 15!")

    # Две проверки:
    # Ищем по штрихкоду в базе
    search_res_by_barcode = await get_cartridge_by_barcode(barcode)
    # Ищем по имени в базе 
    search_res_by_name = await get_cartridge_by_name(cartridge_name)
    # обе переменные содержат кортеж (id, cartridge_name, all_barcodes, quantity, last_update)


    # Если одна из переменных содержит результат поиска (или обе), то нужно проверить все варианты
    # ЗАМЕТКА
    # any() используется для проверки, что в результате поиска есть хоть что-то.
    # Сейчас any() не нужен, но можно использовать если функции базы будут меняться.
    # Сейчас в sql запросах используется группировка GROUP BY c.id, и в случае "ненахода" будет возвращаться None, а не кортеж из нонов
    if search_res_by_barcode or search_res_by_name:
        
        # Обе что-то вернули, нужно сравнить айдишники картриджа, которые вернулись по штрихкоду и по имени
        if search_res_by_barcode and search_res_by_name:
            # Если айдишники совпали, значит в базе уже есть этот картридж с таким именем и штрихкодом
            # Можно отправить в вывод и search_res_by_barcode и search_res_by_name, они будут идентичные
            if search_res_by_barcode[0] == search_res_by_name[0]:
                line = f"ID картриджа у результатов поиска по штрих-коду и по имени совпал!"
                line += f"\n\nКартридж со штрих-кодом {barcode} и именем {cartridge_name} есть в базе."
                line += f"\nИмя:                  {search_res_by_barcode[1]}"
                line += f"\nКоличество:   {search_res_by_barcode[3]}"

                barcodes_list = search_res_by_barcode[2].split("; ")
                for i in barcodes_list:
                    line += f"\nШтрих-код:     <b>{i}</b>"

                line += f"\nИзменение:    {search_res_by_barcode[4]}"
                line += f"\nID в базе:         {search_res_by_barcode[0]}"
                line += f"\n\nЕсли необходимо изменить количество по этому штрихкоду, используй команду /updatecount"    
                return await message.answer(f"{line}", parse_mode="HTML")
            
            # Если айдишники не совпали, значит переданные пользователем штрихкод и имя связаны в базе с разными айдишками картриджей.
            # Можно просто через else а не elif, но так нагляднее
            elif search_res_by_barcode[0] != search_res_by_name[0]:
                # Можно вывести инфу по обоим позициям для понимания
                line = f"ID картриджа у результатов поиска по штрих-коду и по имени не совпали!"
                line += f"\n\nВ базе штрих-код {barcode} связан с существующим картриджем."
                line += f"\nИмя:                  <b>{search_res_by_barcode[1]}</b>"
                line += f"\nКоличество:   {search_res_by_barcode[3]}"
                barcodes_list_1 = search_res_by_barcode[2].split("; ")
                for i in barcodes_list_1:
                    line += f"\nШтрих-код:     <b>{i}</b>"
                line += f"\nИзменение:    {search_res_by_barcode[4]}"
                line += f"\nID в базе:         {search_res_by_barcode[0]}"
                

                line += f"\n\nВ базе имя {cartridge_name} связано с существующим картриджем."
                line += f"\nИмя:                  <b>{search_res_by_name[1]}</b>"
                line += f"\nКоличество:   {search_res_by_name[3]}"

                barcodes_list_2 = search_res_by_name[2].split("; ")
                for i in barcodes_list_2:
                    line += f"\nШтрих-код:     <b>{i}</b>"

                line += f"\nИзменение:    {search_res_by_name[4]}"
                line += f"\nID в базе:         {search_res_by_name[0]}"
                line += f"\n\n\nЕсли необходимо изменить количество по этим позициям, используй команду /updatecount"
                return await message.answer(f"{line}", parse_mode="HTML")
        # Если вернулся только результат по штрихкоду, но не вернулся по имени, говорим об этом пользователю и выводим результат по штрихкоду
        if search_res_by_barcode:
            line = f"Картридж со штрих-кодом {barcode} уже есть в базе.\n"
            line += f"\nИмя:                  {search_res_by_barcode[1]}"
            line += f"\nКоличество:   {search_res_by_barcode[3]}"

            barcodes_list = search_res_by_barcode[2].split("; ")
            for i in barcodes_list:
                line += f"\nШтрих-код:     <b>{i}</b>"

            line += f"\nИзменение:    {search_res_by_barcode[4]}"
            line += f"\nID в базе:         {search_res_by_barcode[0]}"
            line += f"\n\nЕсли необходимо изменить количество по этому штрихкоду, используй команду /updatecount"    
            return await message.answer(f"{line}", parse_mode="HTML")
        # Если вернулся только результат по имени, но не вернулся по штриху, говорим об этом пользователю и выводим результат по имени
        elif search_res_by_name:
            line = f"Картридж с именем {cartridge_name} уже есть в базе.\n"
            line += f"\nИмя:                  {search_res_by_name[1]}"
            line += f"\nКоличество:   {search_res_by_name[3]}"

            barcodes_list = search_res_by_name[2].split("; ")
            for i in barcodes_list:
                line += f"\nШтрих-код:     <b>{i}</b>"

            line += f"\nИзменение:    {search_res_by_name[4]}"
            line += f"\nID в базе:         {search_res_by_name[0]}"
            line += f"\n\nЕсли необходимо изменить количество по этому имени, используй команду /updatecount"    
            return await message.answer(f"{line}", parse_mode="HTML")
        
    # Если обе вернули None, можно вставлять новый картридж с этими данными.
    else:
        # Запускаем функцию вставки нового картриджа, передавая ей штрихкод, имя и количество.
        if await insert_new_cartridge(barcode, cartridge_name, int(quantity)):
            # Проверяем, что картридж добавился, вызывая функцию поиска по штрихкоду, отправляем результат пользователю.
            await message.answer(f"Операция по добавлению выполнена!\
                                \nОтправка тестового запроса к базе по этой позиции:", parse_mode="HTML")
            new_cartridge_data = await get_cartridge_by_barcode(barcode)


            line = f"\nИмя:                  {new_cartridge_data[1]}"
            line += f"\nКоличество:   {new_cartridge_data[3]}"
            barcodes_list = new_cartridge_data[2].split("; ")
            for i in barcodes_list:
                line += f"\nШтрих-код:     <b>{i}</b>"

            line += f"\nИзменение:    {new_cartridge_data[4]}"
            line += f"\nID в базе:         {new_cartridge_data[0]}"
            await message.answer(f"{line}", parse_mode="HTML")

        else:
            return await message.answer(f"Операция по добавлению не выполнена!\
                                \nВозникла ошибка при вставке в базу.", parse_mode="HTML")

# Хэндлер для удаления картриджа из базы
@rt.message(Command("delete"))
async def insert(message: Message, command: CommandObject, bot:Bot) -> Message | None:
    if not command.args:
        return await message.answer("Команда обновления количества картриджей в базе требует аргументов."
                            "<b>\n/delete ID</b>"
                            "\n\nПараметр ID - уникальный ID в базе, посмотреть все можно выведя список /list"
                            "\nАккуратнее с этой командой, дополнительного предупреждения после вызова нет."

                            "\n\nПример синтаксиса:\n"
                            "<b>/delete 1</b>\n",
                                parse_mode="HTML")

    # Нужен только один аргумент, потом сделать нормально
    parts: list[str] = command.args.split()
    if len(parts) != 1:
        return await message.answer("Неверное количество аргументов команды!")
    id: str = parts[0]

    # Проверка аргумента
    if not is_number(id):
        return await message.answer("Количество должно быть числом!")
    if int(id) == 0:
        return await message.answer("ID=0 не может быть в базе!")
    
    # Ищем в базе по ID
    result = await get_cartridge_by_id(id)

    if result:
        await message.answer(f"Картридж найден!\nПоследняя информация об этом картридже из базы:", parse_mode="HTML")
        line = f"\nИмя:                  <b>{result[1]}</b>"
        line += f"\nКоличество:   <b>{result[3]}</b>"
        barcodes_list = result[2].split("; ")
        for i in barcodes_list:
            line += f"\nШтрих-код:     <b>{i}</b>"

        line += f"\nИзменение:    <b>{result[4]}</b>"
        line += f"\nID в базе:         <b>{result[0]}</b>"
        await message.answer(f"{line}", parse_mode="HTML")

        # Вызов функции базы, можно передать строку от пользователя или строку из базы, разницы нет
        if await delete_cartridge(id):
            return await message.answer(f"Информация по этой позиции успешно удалена из базы!", parse_mode="HTML")
        else:
            return await message.answer(f"Ошибка удаления из базы!\nПодробнее в серверных логах.", parse_mode="HTML")
    else:
        await message.answer(f"Картридж по этому ID не найден!")

# Хэндлер для привязки штрих-кода к картриджу
@rt.message(Command("addbar"))
async def addbar(message: Message, command: CommandObject, bot:Bot) -> Message | None:
    
    if not command.args:
        return await message.answer("Команда добавления штрих-кода для картриджа требует аргументов."
                                "\n<b>/addbar BARCODE ID</b>"
                                "\n\n<b>BARCODE</b>: принимает только новый штрих-код для картриджа."
                                "\n<b>ID</b>: уникальный идентификатор картриджа, посмотреть можно выведя список /list"
                                 "\n\nПример синтаксиса для связки штрикода с картриджем:"
                                "\n/addbar <b>123456789123 13</b>",
                                parse_mode="HTML")

    # Нам нужно только два аргумента
    parts: list[str] = command.args.split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer("Неверное количество аргументов команды!")
    barcode, id = parts

    # Простые проверки аргументов
    if not barcode.isdigit():
        return await message.answer("Штрих-код должен состоять только из цифр!")
    if not is_number(id):
        return await message.answer("ID должен быть числом!")
    if not id.isdigit():
        return await message.answer("ID должен состоять только из цифр!")
    if int(id) == 0:
        return await message.answer("ID не может быть равен 0!")
    
    # Проверка связан ли переданный пользователем штрих-код с каким то картриджем
    # Функция вернет кортеж для картриджа с этим баркодом и None, если нет
    barcode_exist = await get_cartridge_by_barcode(barcode)
    id_exist = await get_cartridge_by_id(id)

    # Если вернется None - т.е. ID не найден, не добавляем
    if not(id_exist):
        return await message.answer(f"Такого ID нет в базе!", parse_mode="HTML")
    
    # Если вернется НЕ None - т.е. этот barcode уже есть в базе, не добавляем
    if barcode_exist:
        await message.answer(f"Этот штрих-код уже связан с картриджем!\nПодробная информация:", parse_mode="HTML")
        line = f"\nИмя:                  <b>{barcode_exist[1]}</b>"
        line += f"\nКоличество:   <b>{barcode_exist[3]}</b>"
        barcodes_list = barcode_exist[2].split("; ")
        for i in barcodes_list:
            line += f"\nШтрих-код:     <b>{i}</b>"

        line += f"\nИзменение:    <b>{barcode_exist[4]}</b>"
        line += f"\nID в базе:         <b>{barcode_exist[0]}</b>"
        return await message.answer(f"{line}", parse_mode="HTML")
                
    if await insert_new_barcode(barcode, id):
        return await message.answer(f"Добавление штрих-кода {barcode} для картриджа с ID={id} выполнено", parse_mode="HTML")
    else:
        return await message.answer(f"Добавление не выполнено!", parse_mode="HTML")
    
@rt.message(Command("delbar"))
async def delbar(message: Message, command: CommandObject, bot:Bot) -> Message | None:
    
    if not command.args:
        return await message.answer("Команда добавления штрих-кода для картриджа требует аргументов."
                                "\n<code><b>/delbar BARCODE ID</b></code>"
                                "\n\n<b>BARCODE</b>: принимает только новый штрих-код для картриджа."
                                "\n<b>ID</b>: уникальный идентификатор картриджа, посмотреть можно выведя список /list"
                                 "\n\nПример синтаксиса для удаления штрикода у картриджа с ID 13:"
                                "\n<code>/delbar 123456789123 13</code>",
                                parse_mode="HTML")

    # Нам нужно только два аргумента
    parts: list[str] = command.args.split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer("Неверное количество аргументов команды!")
    barcode, id = parts

    # Простые проверки аргументов
    if not barcode.isdigit():
        return await message.answer("Штрих-код должен состоять только из цифр!")
    if not is_number(id):
        return await message.answer("ID должен быть числом!")
    if not id.isdigit():
        return await message.answer("ID должен состоять только из цифр!")
    if int(id) == 0:
        return await message.answer("ID не может быть равен 0!")
    
    # Проверка связан ли переданный пользователем штрих-код с каким то картриджем
    # Функция вернет кортеж для картриджа с этим баркодом и None, если нет
    #barcode_exist = await get_cartridge_by_barcode(barcode)
    cartridge = await get_cartridge_by_id(id)

    # Если вернется None - т.е. картридж по ID не найден, выходим с сообщением
    if not(cartridge):
        return await message.answer(f"Такого ID нет в базе!", parse_mode="HTML")
    else:
        # Если вернется НЕ None - этот barcode есть в базе, можем удалять
        barcodes_list = cartridge[2].split("; ")
        if barcode in barcodes_list:
            # Вызываем функцию удаления, вернет False если штрих единственный
            bool_res = await delete_barcode(barcode, cartridge[0])
            if bool_res:
                return await message.answer(f"Удаление успешно выполнено!", parse_mode="HTML")
            else:
                return await message.answer(f"Единственный штрих-код нельзя удалить!", parse_mode="HTML")
        else:
            return await message.answer(f"Переданный штрих-код {barcode} не принадлежит картриджу с ID={cartridge[0]}!", parse_mode="HTML")

# Этот хэндлер сработает на любое текстовое сообщение, 
# которое не перехватили команды выше    
@rt.message()
async def echo_all(message: Message):
    await message.answer("Я не понял, пиши /help")