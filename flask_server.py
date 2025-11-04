# -*- coding: utf-8 -*-
import builtins
import logging
import boto3
from botocore.exceptions import ClientError
from config import DB_NAME, DB_USER, DB_PASSWORD, PG_PORT, PG_CONTAINER, PG_BIN, USE_POSTGRES_DOCKER
from config import IS_UPLOAD_MINIO,MINIO_URL, ACCESS_KEY, SECRET_KEY, BUCKET_BAK, BACKUP_DIR, FILESTORE_DIR, PASSWORD_LOGIN_UI, LOCAL_TZ
if IS_UPLOAD_MINIO:
    s3_client = boto3.client('s3',
                      endpoint_url=MINIO_URL,
                      aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY,
                      config=boto3.session.Config(signature_version='s3v4'))

from flask import Flask, render_template, request, Response, jsonify, redirect, url_for, session
import atexit
import signal
from botocore.exceptions import NoCredentialsError
import zipfile
import time
from datetime import datetime, timedelta
import os
from threading import Thread
import schedule
import subprocess
import sys
import pytz
import psutil
import json
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning,
                        message="'sin' and 'sout' swap memory stats couldn't be determined")


# /////////////////////////// config for logging //////////////////////////////////////
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.getLogger('werkzeug').disabled = True

URL = '/auto-backup/'

if not logger.handlers:
    file_handler = logging.FileHandler("flask.log")
    stream_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

# /////////////////////////////////////////////////////////////////////////////////////////

original_print = builtins.print


def print_with_time(*args, **kwargs):
    timestamp = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    original_print(f"{timestamp} PRINT", *args, **kwargs)


builtins.print = print_with_time
print("Starting flask server")

app = Flask(__name__)

app.secret_key = 'mrhieu!'  # encode for session cookie
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# ensure folder created
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)


@app.route(URL)
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    files = []
    for file_name in os.listdir(BACKUP_DIR):
        file_path = os.path.join(BACKUP_DIR, file_name)
        os.path.isfile(file_path)
        if os.path.isfile(file_path) and (file_name.endswith('.dump') or file_name.endswith('.zip')):
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            file_creation_time = os.path.getctime(file_path)
            files.append({
                'name': file_name,
                'size': round(file_size_mb, 2),
                'creation_time': file_creation_time,
                'is_dump_file': file_name.endswith('.dump')
            })
    files.sort(key=lambda f: (
        0 if f['name'].endswith('.dump') else 1,
        -f['creation_time']
    ))

    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
    next_schedule = midnight.strftime('%Y-%m-%d %H:%M:%S')
    return render_template('index.html', files=files, next_schedule=next_schedule, password_login=PASSWORD_LOGIN_UI)


@app.route(f'{URL}disk_info', methods=['GET'])
def get_disk_info():
    partitions = psutil.disk_partitions()
    disk_info = []
    for partition in partitions:
        if partition.mountpoint == '/':
            usage = psutil.disk_usage(partition.mountpoint)
            disk_info.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'fstype': partition.fstype,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': usage.percent
            })
    return jsonify(disk_info)


@app.route(f'{URL}cpu_info', methods=['GET'])
def get_cpu_info():
    cpu_per_core = psutil.cpu_percent(percpu=True)
    cpu_model = get_cpu_model()
    total_cores = psutil.cpu_count(logical=True)
    cpu_info = {
        "cpu_per_core": cpu_per_core,
        "cpu_model": cpu_model,
        "total_cores": total_cores
    }
    return jsonify(cpu_info)


@app.route(f'{URL}cpu_update', methods=['GET'])
def cpu_update():
    cpu_per_core = psutil.cpu_percent(percpu=True)
    ram_info = psutil.virtual_memory()
    ram_total = ram_info.total / (1024 * 1024)  # Convert to MB
    ram_used = (ram_info.total - ram_info.available) / (1024 * 1024)
    swap_info = psutil.swap_memory()
    swap_used = swap_info.used / (1024 * 1024)  # Convert to MB
    swap_total = swap_info.total / (1024 * 1024)  # Convert to MB
    return jsonify({
        "cpu_per_core": cpu_per_core,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "swap_used": swap_used,
        "swap_total": swap_total
    })


def get_cpu_model():
    try:
        result = subprocess.run(
            ['lscpu'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in result.stdout.splitlines():
            if line.startswith("Model name:"):
                model_name = line.split(":")[1].strip()
                return model_name
        return "Unknown CPU Model"
    except Exception as e:
        return f"Error retrieving CPU model: {str(e)}"


@app.route(f'{URL}login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        entered_password = request.form.get('password')
        if entered_password == PASSWORD_LOGIN_UI:
            session.permanent = True
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Wrong password. Please try again.')
    return render_template('login.html')


@app.route(f'{URL}logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route(f'{URL}delete/<filename>', methods=['POST'])
def delete(filename):
    file_path = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        print("File is deleted successfully !")
    return redirect(url_for('index'))


import boto3
from botocore.exceptions import ClientError
import shutil

# Thêm vào đầu file, sau phần import config
if IS_UPLOAD_MINIO:
    s3_client = boto3.client('s3',
                      endpoint_url=MINIO_URL,
                      aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY,
                      config=boto3.session.Config(signature_version='s3v4'))


@app.route(f'{URL}restore/<filename>', methods=['POST'])
def restore(filename):
    from odoo_backup_manager import OdooBackupManager
    from config import ODOO_URL, ODOO_MASTER_PASSWORD, LOCAL_TZ, DB_NAME
    
    file_path = os.path.join(BACKUP_DIR, filename)
    
    if not os.path.exists(file_path):
        print(f"[ERROR] Backup file not found: {file_path}")
        return redirect(url_for('index'))
    
    # Initialize Odoo Backup Manager
    backup_manager = OdooBackupManager(ODOO_URL, ODOO_MASTER_PASSWORD, LOCAL_TZ)
    
    print(f"[INFO] Starting restore from: {filename}")
    
    # Option 1: Drop existing database first (recommended)
    print(f"[INFO] Dropping existing database: {DB_NAME}")
    drop_success, drop_msg = backup_manager.drop_database(DB_NAME)
    if drop_success:
        print(f"[INFO] {drop_msg}")
    else:
        print(f"[WARNING] Could not drop database: {drop_msg}")
    
    # Restore database
    success, message = backup_manager.restore_database(file_path, db_name=DB_NAME, copy=False)
    
    if success:
        print(f"[INFO] {message}")
    else:
        print(f"[ERROR] {message}")
    
    return redirect(url_for('index'))

# Route để sync files từ MinIO về local
@app.route(f'{URL}sync-from-minio', methods=['POST'])
def sync_from_minio():
    if not IS_UPLOAD_MINIO:
        return jsonify({'error': 'MinIO is not enabled in config'}), 400
    
    try:
        print("[INFO] Starting sync from MinIO...")
        response = s3_client.list_objects_v2(Bucket=BUCKET_BAK)
        
        if 'Contents' not in response:
            print("[INFO] MinIO bucket is empty")
            return jsonify({'message': 'No files in MinIO bucket', 'files': []}), 200
        
        synced_files = []
        skipped_files = []
        
        for obj in response['Contents']:
            filename = obj['Key']
            local_path = os.path.join(BACKUP_DIR, filename)
            minio_size = obj['Size']
            
            # Check if download needed
            should_download = False
            reason = ""
            
            if not os.path.exists(local_path):
                should_download = True
                reason = "file not exists locally"
            elif os.path.isdir(local_path):
                # If local path is a directory, remove it and download
                should_download = True
                reason = "local path is a directory, will be replaced"
                shutil.rmtree(local_path)
            elif os.path.getsize(local_path) == 0:
                should_download = True
                reason = "local file is 0 bytes"
            elif os.path.getsize(local_path) != minio_size:
                should_download = True
                reason = f"size mismatch (local: {os.path.getsize(local_path)}, minio: {minio_size})"
            
            if should_download:
                print(f"[INFO] Downloading {filename} from MinIO ({reason})...")
                try:
                    s3_client.download_file(BUCKET_BAK, filename, local_path)
                    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
                    synced_files.append({
                        'name': filename,
                        'size_mb': round(file_size_mb, 2)
                    })
                    print(f"[INFO] Downloaded {filename} successfully ({file_size_mb:.2f} MB)")
                except Exception as download_error:
                    print(f"[ERROR] Failed to download {filename}: {download_error}")
            else:
                skipped_files.append(filename)
                print(f"[INFO] Skipped {filename} (already synced)")
        
        message = f'Successfully synced {len(synced_files)} file(s) from MinIO'
        if skipped_files:
            message += f', skipped {len(skipped_files)} file(s) (already up-to-date)'
        
        print(f"[INFO] Sync completed: {message}")
        
        return jsonify({
            'message': message,
            'files': [f['name'] for f in synced_files],
            'synced_count': len(synced_files),
            'skipped_count': len(skipped_files)
        }), 200
        
    except Exception as e:
        error_msg = f"Sync failed: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route(f'{URL}/backup-now', methods=['POST'])
def backup_now():
    try:
        print("Manualy backup starting...")
        backup()
    except Exception as e:
        print(f"Error during backup: {e}")
    return redirect(url_for('index'))


@app.route(f"{URL}log")
def view_log():
    log_path = "flask.log"
    max_lines = 1000
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-max_lines:]
    except FileNotFoundError:
        return "Log file not found."

    def format_line(line):
        if "ERROR" in line:
            return f'<div style="color: red;">{line}</div>'
        elif "WARNING" in line:
            return f'<div style="color: orange;">{line}</div>'
        elif "INFO" in line:
            return f'<div style="color: green;">{line}</div>'
        elif "DEBUG" in line:
            return f'<div style="color: blue;">{line}</div>'
        else:
            return f'<div>{line}</div>'
    html = ''.join(format_line(line) for line in lines)
    return html

# ////////////////////////////////////////////////////////////////////////// schedule //////////////////


def backup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backup_script = os.path.join(current_dir, 'backup.py')
    try:
        subprocess.run([sys.executable, backup_script], check=True)
        print("Backup completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e}")


def job():
    print(
        f"Running backup at {datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')} ...")
    backup()


def schedule_midnight_job():
    schedule.clear('midnight')
    schedule.every().day.at("17:00").do(job).tag('midnight')  # 17:00 UTC = 00:00 VN
    print(f"Backup scheduled daily at 00:00 ({LOCAL_TZ})")

# ////////////////////////////////////////////////////////////////////////////////


def close_server():
    print("Server is closing.")
    os.kill(os.getpid(), signal.SIGTERM)


atexit.register(close_server)

# Start the Flask app in a separate thread


def flask_run():
    app.run(host='0.0.0.0', port=8080)  # Changed port to 8009


if __name__ == '__main__':
    flask_thread = Thread(target=flask_run)
    flask_thread.start()
    schedule_midnight_job()
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("App shutdown...")
        os.kill(os.getpid(), signal.SIGTERM)
