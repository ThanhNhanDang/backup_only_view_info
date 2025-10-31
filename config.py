
USE_POSTGRES_DOCKER = False
IS_UPLOAD_MINIO = False

DB_NAME = "inah"
DB_USER = "odoo"
DB_PASSWORD = "123456aA@"
PG_PORT = 5432
PG_BIN = '/usr/bin/'
PG_CONTAINER = 'postgres-db'
DUMP_PREFIX = DB_NAME

# === Configuration Minio ===
MINIO_URL = "http://192.168.1.10:12899" # URL API Minio
ACCESS_KEY = "admin" #ACCESS_KEY created  on UI minio or ROOT_USER
SECRET_KEY = "autonsi1234"# SECRET_KEY created on UI minio or ROOT_USER_PASSWORD
BUCKET_BAK = "backups"

FILESTORE_DIR = "/odoo/.local/share/Odoo/filestore/"
BACKUP_DIR = "/home/administrator/pg_dumps"
MAX_FILES_DUMP = 3

#login UI
PASSWORD_LOGIN_UI = 'autonsi1234'


# location /auto-backup/ {
#         proxy_pass http://localhost:8008/auto-backup/;
#         proxy_http_version 1.1;
#         proxy_set_header Upgrade $http_upgrade;
#         proxy_set_header Connection 'upgrade';
#         proxy_set_header Host $host;
#         proxy_set_header X-Real-IP $remote_addr;
#         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#         proxy_set_header X-Forwarded-Proto $scheme;
#         proxy_cache_bypass $http_upgrade;

#         add_header 'Access-Control-Allow-Origin' '*';
#         add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
#         add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';

#         # Handle OPTIONS for CORS
#         if ($request_method = 'OPTIONS') {
#             add_header 'Access-Control-Allow-Origin' '*';
#             add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
#             add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
#             add_header 'Access-Control-Max-Age' 1728000;
#             add_header 'Content-Type' 'text/plain; charset=utf-8';
#             add_header 'Content-Length' 0;
#             return 204;
#         }
#     }