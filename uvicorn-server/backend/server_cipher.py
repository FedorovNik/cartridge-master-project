"""
CartridgeMaster - модуль для шифрования и расшифровки данных.

Содержит функции для работы с AES шифрованием при обмене данными с ТСД.
"""

import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad
from config import AES_KEY


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
