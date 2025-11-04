# -*- coding: utf-8 -*-
import os
import datetime
import boto3
from minio.error import S3Error
import builtins

from config import (DB_NAME, BACKUP_DIR, MAX_FILES_DUMP, IS_UPLOAD_MINIO,
                   MINIO_URL, ACCESS_KEY, SECRET_KEY, BUCKET_BAK, LOCAL_TZ,
                   ODOO_URL, ODOO_MASTER_PASSWORD)
from odoo_backup_manager import OdooBackupManager

# Setup print with timestamp
original_print = builtins.print

def print_with_time(*args, **kwargs):
    timestamp = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    original_print(f"{timestamp} PRINT", *args, **kwargs)

builtins.print = print_with_time

# Initialize MinIO if enabled
if IS_UPLOAD_MINIO:
    s3 = boto3.client('s3',
                      endpoint_url=MINIO_URL,
                      aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY,
                      config=boto3.session.Config(signature_version='s3v4'))
    
    try:
        s3.head_bucket(Bucket=BUCKET_BAK)
        print(f"Bucket '{BUCKET_BAK}' already exists.")
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Bucket '{BUCKET_BAK}' does not exist. Creating it...")
            s3.create_bucket(Bucket=BUCKET_BAK)
            print(f"Bucket '{BUCKET_BAK}' created.")

# Create backup directory if not exists
os.makedirs(BACKUP_DIR, exist_ok=True)

# Initialize Odoo Backup Manager
backup_manager = OdooBackupManager(ODOO_URL, ODOO_MASTER_PASSWORD, LOCAL_TZ)

print("Starting backup process using Odoo Database Manager...")

# Perform backup (zip format includes filestore automatically)
success, filename, content = backup_manager.backup_database(DB_NAME, backup_format='zip')

if success:
    # Save backup file
    backup_path = os.path.join(BACKUP_DIR, filename)
    with open(backup_path, 'wb') as f:
        f.write(content)
    print(f"Backup saved to: {backup_path}")
    
    # Get list of existing backup files
    dump_files = []
    for file in os.listdir(BACKUP_DIR):
        if file.endswith('.zip') or file.endswith('.dump'):
            file_path = os.path.join(BACKUP_DIR, file)
            dump_files.append({
                'filename': file,
                'filepath': file_path,
                'mtime': os.path.getmtime(file_path)
            })
    
    # Sort by modification time (newest first)
    dump_files.sort(key=lambda x: x['mtime'], reverse=True)
    
    # Delete old backups if exceeds MAX_FILES_DUMP
    if len(dump_files) > MAX_FILES_DUMP:
        files_to_delete = dump_files[MAX_FILES_DUMP:]
        for file_info in files_to_delete:
            print(f"Deleting old backup: {file_info['filename']}")
            os.remove(file_info['filepath'])
            
            # Also delete from MinIO if enabled
            if IS_UPLOAD_MINIO:
                try:
                    s3.delete_object(Bucket=BUCKET_BAK, Key=file_info['filename'])
                    print(f"Deleted from MinIO: {file_info['filename']}")
                except S3Error as e:
                    print(f"Failed to delete from MinIO: {e}")
    
    # Upload to MinIO if enabled
    if IS_UPLOAD_MINIO:
        try:
            with open(backup_path, "rb") as data:
                s3.upload_fileobj(data, BUCKET_BAK, filename)
            print(f"Uploaded {filename} to MinIO bucket: {BUCKET_BAK}")
        except S3Error as e:
            print(f"MinIO upload failed: {e}")
    
    print("Backup completed successfully!")
else:
    print(f"Backup failed: {filename}")  # filename contains error message