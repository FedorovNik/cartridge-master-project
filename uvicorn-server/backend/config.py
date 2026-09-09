"""
CartridgeMaster - конфигурация и константы приложения.
"""

import os

# Имя локальной БД
DB_NAME = os.getenv("DB_NAME", "inventory.db")

# Ключ для ТСДшника
AES_KEY = os.getenv("AES_KEY", "My_Secret_Key_16")

# LDAP-конфигурация для аутентификации
LDAP_SERVER = os.getenv("LDAP_SERVER", "")
DOMAIN = os.getenv("DOMAIN", "NIZHBEL")
SERVICE_USER = os.getenv("SERVICE_USER", "")
SERVICE_PASSWORD = os.getenv("SERVICE_PASSWORD", "")
LDAP_SEARCH_BASE = os.getenv("LDAP_SEARCH_BASE", "")
GROUP_DN = os.getenv("GROUP_DN", "")

# Локальный пользователь для резервной авторизации
SYSMASTER_USERNAME = os.getenv("SYSMASTER_USERNAME", "")
SYSMASTER_PASSWORD = os.getenv("SYSMASTER_PASSWORD", "")

# Настройки почтового сервера для уведомлений
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = os.getenv("SMTP_PORT", "")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
