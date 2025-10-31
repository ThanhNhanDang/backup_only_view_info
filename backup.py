# -*- coding: utf-8 -*-
import subprocess
import os
import time
import datetime

from minio import Minio
from minio.error import S3Error
import json
import requests
from requests.auth import HTTPBasicAuth
import zipfile
import boto3
from botocore.exceptions import NoCredentialsError

from config import DB_NAME, DB_USER, DB_PASSWORD, PG_PORT, DUMP_PREFIX, USE_POSTGRES_DOCKER, PG_CONTAINER
from config import BACKUP_DIR, FILESTORE_DIR, MAX_FILES_DUMP, PG_BIN
from config import MINIO_URL, ACCESS_KEY, SECRET_KEY, BUCKET_BAK, IS_UPLOAD_MINIO, LOCAL_TZ

import pytz


import builtins

original_print = builtins.print


def print_with_time(*args, **kwargs):
    timestamp = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    original_print(f"{timestamp} PRINT", *args, **kwargs)


builtins.print = print_with_time


if IS_UPLOAD_MINIO:
    # Initialize MinIO client
    s3 = boto3.client('s3',
                      endpoint_url=MINIO_URL,
                      aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY,
                      config=boto3.session.Config(signature_version='s3v4'))  # AWS Signature Version 4

    # Check if the bucket backups, create if not
    try:
        s3.head_bucket(Bucket=BUCKET_BAK)
        print(f"Bucket '{BUCKET_BAK}' already exists.")
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Bucket '{BUCKET_BAK}' does not exist. Creating it...")
            s3.create_bucket(Bucket=BUCKET_BAK)
            print(f"Bucket '{BUCKET_BAK}' created.")


if USE_POSTGRES_DOCKER:
    # Filestore nằm trong container
    filestore_dir = f"/var/lib/odoo/filestore/{DB_NAME}"
    # Sử dụng docker exec để access
    ODOO_CONTAINER = os.getenv('ODOO_CONTAINER', 'inah-odoo')  # Thêm vào config.py
else:
    filestore_dir = FILESTORE_DIR + DB_NAME


# ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
print("Checking backup database...")
now = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d_%H-%M-%S")
today = datetime.date.today()
dump_filename = f"{DUMP_PREFIX}_{now}.dump"
dump_path = os.path.join(BACKUP_DIR, dump_filename)
os.makedirs(BACKUP_DIR, exist_ok=True)


number_of_files = 0
oldest_file = None  # To store the oldest file if we need to delete it
dump_files = []  # Lưu trữ danh sách các file dump
for filename in os.listdir(BACKUP_DIR):
    if filename.endswith(".dump"):

        file_path = os.path.join(BACKUP_DIR, filename)

        number_of_files += 1

        # Track the oldest file if number_of_files exceeds MAX_FILES_DUMP
        if not oldest_file or os.path.getmtime(file_path) < os.path.getmtime(oldest_file):
            oldest_file = file_path
        dump_files.append({
            'filename': filename,
            'filepath': file_path,
            'mtime': os.path.getmtime(file_path)
        })    
# Sắp xếp files theo thời gian tạo (mới nhất trước)
dump_files.sort(key=lambda x: x['mtime'], reverse=True)            
# === Dump the PostgreSQL database ===

if USE_POSTGRES_DOCKER:
    print("Dumping using Postgres docker ....")
    dump_cmd = (
        f'docker exec -i {PG_CONTAINER} pg_dump -Fc '
        f'--username={DB_USER} --dbname={DB_NAME} > "{dump_path}"'
    )
else:
    dump_cmd = (
        f'sudo -u odoo "{PG_BIN}pg_dump" -p {PG_PORT} -Fc '
        f'--username={DB_USER} --dbname={DB_NAME} > "{dump_path}"'
    )


print(f"Dumping database using: {dump_cmd}")
try:
    subprocess.run(dump_cmd, shell=True, check=True)
    print(f"Database dumped to: {dump_path}")

    number_of_files = number_of_files + 1
except subprocess.CalledProcessError as e:
    print(f"pg_dump failed: {e}")
    exit(1)

# Check if number of files exceeds MAX_FILES_DUMP, and if so, delete the oldest file
if number_of_files > MAX_FILES_DUMP:
    if oldest_file:
        print(f"Too many files, deleting the oldest file: {oldest_file}")
        os.remove(oldest_file)


if IS_UPLOAD_MINIO:

    # upload dump to minio
    try:

        object_name = os.path.basename(dump_path)
        with open(dump_path, "rb") as data:
            s3.upload_fileobj(data, BUCKET_BAK, object_name)

        print(f"Uploaded {object_name} to MinIO bucket: {BUCKET_BAK}")
    except S3Error as e:
        print(f"MinIO upload failed: {e}")

    # Optional: delete the oldest file on MinIO
    if number_of_files > MAX_FILES_DUMP and oldest_file:
        try:
            oldest_object = os.path.basename(oldest_file)
            s3.delete_object(Bucket=BUCKET_BAK, Key=oldest_object)
            print(f"Deleted oldest file from MinIO: {oldest_object}")
        except S3Error as e:
              print(f"MinIO upload failed: {e}")
              
              
              
        # Optional: delete the oldest file on MinIO
        # Fixed: Check if we have enough files and access the correct dictionary key
        if number_of_files > MAX_FILES_DUMP and len(dump_files) > 2:  # Index 2 = file thứ 3
            try:
                # Use the 'filename' key from the dictionary
                oldest_object = dump_files[2]['filename']
                s3.delete_object(Bucket=BUCKET_BAK, Key=oldest_object)
                print(f"Deleted oldest file from MinIO: {oldest_object}")
            except S3Error as e:
                print(f"Failed to delete oldest file from MinIO: {e}")
            except IndexError as e:
                print(f"Index error when accessing dump_files: {e}")
            
                 
        
#////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

print("Checking backup filestore...")

# Constants
last_check_file = "/tmp/last_filestore_check.txt"


# Get current datetime
now = datetime.datetime.now(LOCAL_TZ)

# Load last check time or default to 7 days ago
if os.path.exists(last_check_file):
    with open(last_check_file, "r") as f:
        last_check_str = f.read().strip()
        if not last_check_str:
            last_check_dt = False
        else:
            naive_dt = datetime.datetime.strptime(
                last_check_str, "%Y-%m-%d %H:%M:%S")
            last_check_dt = LOCAL_TZ.localize(naive_dt)

else:
    last_check_dt = False  # now - datetime.timedelta(days=7)

# Prepare zip filename
zip_name = f"filestore_backup_{now.strftime('%Y-%m-%d_%H-%M-%S')}.zip"
zip_path = os.path.join(BACKUP_DIR, zip_name)
if os.path.exists(BACKUP_DIR):
    if USE_POSTGRES_DOCKER:
        # Copy filestore từ container ra host trước
        temp_filestore = os.path.join(BACKUP_DIR, "temp_filestore")
        os.makedirs(temp_filestore, exist_ok=True)
        
        copy_cmd = f"docker cp {ODOO_CONTAINER}:{filestore_dir} {temp_filestore}"
        print(f"Copying filestore from container: {copy_cmd}")
        
        try:
            subprocess.run(copy_cmd, shell=True, check=True)
            source_dir = os.path.join(temp_filestore, DB_NAME)
        except subprocess.CalledProcessError as e:
            print(f"Failed to copy filestore: {e}")
            source_dir = None
    else:
        source_dir = filestore_dir
    
    if source_dir and os.path.exists(source_dir):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_ctime_native = datetime.datetime.fromtimestamp(
                        os.path.getctime(file_path))
                    file_ctime = LOCAL_TZ.localize(file_ctime_native)
                    if not last_check_dt or file_ctime > last_check_dt:
                        arcname = os.path.relpath(file_path, source_dir)
                        zipf.write(file_path, arcname=os.path.join(
                            DB_NAME, arcname))
        
        # Xóa temp folder
        if USE_POSTGRES_DOCKER and os.path.exists(temp_filestore):
            import shutil
            shutil.rmtree(temp_filestore)

    # Save current time as last check
    with open(last_check_file, "w") as f:
        f.write(now.strftime("%Y-%m-%d %H:%M:%S"))

    if IS_UPLOAD_MINIO:
        # upload to minio zip_path
        try:

            object_name = os.path.basename(zip_path)
            with open(zip_path, "rb") as data:
                s3.upload_fileobj(data, BUCKET_BAK, object_name)

            print(f"Uploaded {object_name} to MinIO bucket: {BUCKET_BAK}")
        except S3Error as e:
            print(f"MinIO upload failed: {e}")

    print(f"ZIP backup created at: {zip_path}")