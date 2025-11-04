import pytz

# Timezone cho GMT+7 (Asia/Bangkok)
LOCAL_TZ = pytz.timezone('Asia/Bangkok')
import shutil

USE_POSTGRES_DOCKER = True
IS_UPLOAD_MINIO = True

DB_NAME = "inah_2025-01-14"
DB_USER = "odoo"
DB_PASSWORD = "MkWkrQrD8sA7oEOPhqLVpmXbWswuoop0yGEkmVNkdeMWIqBj"
PG_PORT = 5432
PG_BIN = '/usr/bin/'
PG_CONTAINER = 'postgres_db'
DUMP_PREFIX = DB_NAME

# === Odoo Configuration ===
ODOO_URL = "http://localhost:18000"  # URL của Odoo instance
ODOO_MASTER_PASSWORD = "JkM5DvrD3wWSSMGP"  # Master password của Odoo (trong odoo.conf)

# === Configuration Minio ===
MINIO_URL = "http://192.168.1.211:9000"
ACCESS_KEY = "autonsi"
SECRET_KEY = "autonsi1234"
BUCKET_BAK = "auto-backup"

FILESTORE_DIR = "/odoo/.local/share/Odoo/filestore/"
BACKUP_DIR = "/home/administrator/pg_dumps"
MAX_FILES_DUMP = 7

# Login UI
PASSWORD_LOGIN_UI = 'autonsi1234'