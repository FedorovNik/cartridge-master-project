import base64
from Crypto.Cipher import AES

# Ключ и ответ сервера
key = b"My_Secret_Key_16"
response_b64 = "pZD0Pk0OntxYBCNWtbJMGGnlf3y/BMdSTYFnMrDKDOXqX6rVa4ZNwzXT5dTJgJlKobJJ0WE0HVIRDvxVMLSNDQ=="

# Декодируем Base64
raw_data = base64.b64decode(response_b64)

# Достаем IV (первые 16 байт) и сам шифротекст
iv = raw_data[:16]
ciphertext = raw_data[16:]

# Расшифровываем
cipher = AES.new(key, AES.MODE_CBC, iv)
decrypted_bytes = cipher.decrypt(ciphertext)

# Убираем паддинг (последние байты показывают, сколько лишнего добавлено)
padding_len = decrypted_bytes[-1]
clean_text = decrypted_bytes[:-padding_len].decode('utf-8')

print(f"Ответ сервера: {clean_text}")