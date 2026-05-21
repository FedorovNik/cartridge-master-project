import smtplib
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from config import SMTP_SERVER, SMTP_PORT, EMAIL_ADDRESS, EMAIL_PASSWORD

logger = logging.getLogger("my_custom_logger")

smtp_server = SMTP_SERVER
smtp_port = SMTP_PORT
email_address = EMAIL_ADDRESS
email_password = EMAIL_PASSWORD


def _send_email_sync(recipient, subject, html_body):
    """
    Отправляет одиночное HTML-письмо без резервной текстовой версии
    """
    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(email_address, email_password)
        
        message = EmailMessage()
        message["From"] = email_address
        message["To"] = recipient
        message["Subject"] = subject
        
        # Обязательные заголовки для корректного парсинга в GLPI
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid()
        message['User-Agent'] = 'Mozilla Thunderbird'
        
        # Устанавливаем только HTML-контент, сохраняя читаемость (cte='8bit')
        message.set_content(html_body, subtype='html', charset='utf-8', cte='8bit')
        
        server.send_message(message)
        server.quit()
        logger.info(f"MAILSERVICE  - 'OK - Уведомление успешно отправлено на {recipient}'")
        return True
    except Exception as e:
        logger.error(f"MAILSERVICE  - 'ERR - Ошибка при отправке на {recipient}: {e}'")
        return False


async def send_low_stock_notifications(emails: list, low_stock_cartridges: list):
    """
    Отправляет HTML-уведомления о низком запасе картриджей с инлайновыми стилями.
    Стили полностью перенесены из тега <style> внутрь элементов с добавлением !important.
    """
    if not emails or not low_stock_cartridges:
        return 0
    
    # --- СБОРКА HTML С ИНЛАЙН-СТИЛЯМИ ---
    html_body = """
    <html>
    <body style="font-family: Arial, sans-serif !important; color: #333333 !important;">
        <h3 style="color: #2c3e50 !important; font-family: Arial, sans-serif !important; margin-bottom: 15px !important;">Список расходников:</h3>
        
        <table style="border-collapse: collapse !important; width: 100% !important; max-width: 600px !important; margin-top: 15px !important; font-family: Arial, sans-serif !important; border: 1px solid #dddddd !important;">
            <thead>
                <tr>
                    <th style="border: 1px solid #dddddd !important; padding: 10px !important; background-color: #f4f4f4 !important; font-weight: bold !important; text-align: left !important; color: #333333 !important;">Модель</th>
                    <th style="border: 1px solid #dddddd !important; padding: 10px !important; background-color: #f4f4f4 !important; font-weight: bold !important; text-align: left !important; color: #333333 !important;">Текущий запас</th>
                    <th style="border: 1px solid #dddddd !important; padding: 10px !important; background-color: #f4f4f4 !important; font-weight: bold !important; text-align: left !important; color: #333333 !important;">Необходимый минимум</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for cartridge in low_stock_cartridges:
        html_body += f"""
                <tr>
                    <td style="border: 1px solid #dddddd !important; padding: 10px !important; text-align: left !important; color: #333333 !important; background-color: #ffffff !important;">{cartridge['name']}</td>
                    <td style="border: 1px solid #dddddd !important; padding: 10px !important; text-align: left !important; color: #d9534f !important; font-weight: bold !important; background-color: #ffffff !important;">{cartridge['quantity']}</td>
                    <td style="border: 1px solid #dddddd !important; padding: 10px !important; text-align: left !important; color: #333333 !important; background-color: #ffffff !important;">{cartridge['min_qty']}</td>
                </tr>
        """
        
    html_body += """
            </tbody>
        </table>
        <div style="margin-top: 25px !important; font-size: 0.85em !important; color: #777777 !important; font-family: Arial, sans-serif !important; border-top: 1px dashed #cccccc !important; padding-top: 5px !important; max-width: 600px !important;">
            <p>Это автоматическое уведомление формируется если текущий запас хотя бы одного картриджа опускается строго ниже заданного для него минимума.</p>
            <p></p>
        </div>
    </body>
    </html>
    """
    
    subject = "CartridgeMaster: уведомление о закупке"
    sent_count = 0
    
    try:
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=5)
        
        tasks = []
        for recipient in emails:
            task = loop.run_in_executor(executor, _send_email_sync, recipient, subject, html_body)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        sent_count = sum(1 for result in results if result)
        
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")
        return 0
    
    return sent_count