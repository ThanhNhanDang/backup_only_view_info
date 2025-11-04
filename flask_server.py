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
    if filename.endswith('.dump'):
        file_path = os.path.join(BACKUP_DIR, filename)
        # Restore database
        if USE_POSTGRES_DOCKER:
            print("Restore in docker mode")
            try:
                # Verify file size
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    print(f"[ERROR] File {filename} is 0 bytes!")
                    return redirect(url_for('index'))
                
                print(f"[INFO] File size: {file_size / (1024*1024):.2f} MB")
                
                # Clean up existing file/directory in container first
                print("[INFO] Cleaning up old files in container...")
                cleanup_old_cmd = ['docker', 'exec', PG_CONTAINER, 'rm', '-rf', f'/tmp/{filename}']
                subprocess.run(cleanup_old_cmd, stderr=subprocess.DEVNULL)
                
                print("Copying file dump into container...")
                # Copy file vào container
                docker_cp_cmd = ['docker', 'cp', file_path, f'{PG_CONTAINER}:/tmp/{filename}']
                subprocess.run(docker_cp_cmd, check=True)
                print(f"[INFO] File copied successfully to container")
                
                # Verify file trong container
                verify_cmd = ['docker', 'exec', PG_CONTAINER, 'ls', '-lh', f'/tmp/{filename}']
                verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
                print(f"[INFO] File in container: {verify_result.stdout}")
                
                # Restore database
                restore_cmd = [
                    'docker', 'exec', '-i', PG_CONTAINER,
                    'pg_restore',
                    '-U', DB_USER,
                    '-p', str(PG_PORT),
                    '-C',
                    '-d', 'postgres',
                    f'/tmp/{filename}'
                ]
                print(f"[INFO] Running restore command in Docker: {' '.join(restore_cmd)}")
                
                result = subprocess.run(restore_cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"[ERROR] pg_restore stderr: {result.stderr}")
                    print(f"[ERROR] pg_restore stdout: {result.stdout}")
                    print(f"[ERROR] Please DROP or RENAME old database before restore.")
                else:
                    print("[INFO] Database restore completed successfully in Docker.")
                    
                # Clean up file trong container
                cleanup_cmd = ['docker', 'exec', PG_CONTAINER, 'rm', '-f', f'/tmp/{filename}']
                subprocess.run(cleanup_cmd)
                print(f"[INFO] Cleaned up temp file in container")
                    
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Command failed: {e}")
            except Exception as ex:
                print(f"[ERROR] Unexpected error: {ex}")
        else:
            # Non-Docker mode
            print("Postgres is installed directly on the server, not using Docker.")
            try:
                if not os.path.exists(file_path):
                    print(f"[ERROR] Backup file not found: {file_path}")
                    return redirect(url_for('index'))
                    
                restore_cmd = [
                    'sudo', '-u', 'odoo',
                    os.path.join(PG_BIN, 'pg_restore'),
                    '-U', DB_USER,
                    '-p', str(PG_PORT),
                    '-C',
                    '-d', 'postgres',
                    file_path
                ]
                print(f"[INFO] Running restore command: {' '.join(restore_cmd)}")
                result = subprocess.run(restore_cmd, check=True)
                print(f"[INFO] Database restore completed successfully.")
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] pg_restore failed: {e}")
            except Exception as ex:
                print(f"[ERROR] Unexpected error: {ex}")
        
        # Restore filestore
        try:
            zip_files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')]
            
            # Download zip files từ MinIO nếu không có local
            if IS_UPLOAD_MINIO:
                try:
                    # List all objects trong bucket
                    response = s3_client.list_objects_v2(Bucket=BUCKET_BAK)
                    if 'Contents' in response:
                        minio_zip_files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.zip')]
                        
                        for zip_file in minio_zip_files:
                            local_zip_path = os.path.join(BACKUP_DIR, zip_file)
                            
                            # Download nếu không tồn tại hoặc 0 byte
                            if not os.path.exists(local_zip_path) or os.path.getsize(local_zip_path) == 0:
                                print(f"[INFO] Downloading {zip_file} from MinIO...")
                                s3_client.download_file(BUCKET_BAK, zip_file, local_zip_path)
                                file_size_mb = os.path.getsize(local_zip_path) / (1024 * 1024)
                                print(f"[INFO] Downloaded {zip_file} ({file_size_mb:.2f} MB)")
                                
                                if zip_file not in zip_files:
                                    zip_files.append(zip_file)
                except ClientError as e:
                    print(f"[ERROR] Failed to list/download zip files from MinIO: {e}")
            
            if not zip_files:
                print("[INFO] No filestore zip files found to restore.")
            else:
                ODOO_CONTAINER = os.getenv('ODOO_CONTAINER', 'inah-odoo')
                
                for zip_file in zip_files:
                    zip_path = os.path.join(BACKUP_DIR, zip_file)
                    
                    # Skip if file doesn't exist or is empty
                    if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
                        print(f"[WARNING] Skipping {zip_file} (not found or empty)")
                        continue
                    
                    print(f"[INFO] Restoring filestore from: {zip_file}")
                    
                    if USE_POSTGRES_DOCKER:
                        # Docker mode: Unzip locally then copy to container
                        temp_extract_dir = os.path.join(BACKUP_DIR, 'temp_filestore_extract')
                        
                        try:
                            # Clean up old temp directory
                            if os.path.exists(temp_extract_dir):
                                shutil.rmtree(temp_extract_dir)
                            os.makedirs(temp_extract_dir, exist_ok=True)
                            
                            # Unzip locally
                            print(f"[INFO] Extracting {zip_file} locally...")
                            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                                zip_ref.extractall(temp_extract_dir)
                            print(f"[INFO] Extracted successfully")
                            
                            # Copy extracted files to Odoo container
                            # Find the database folder inside extracted files
                            db_folder = None
                            for item in os.listdir(temp_extract_dir):
                                item_path = os.path.join(temp_extract_dir, item)
                                if os.path.isdir(item_path):
                                    db_folder = item_path
                                    break
                            
                            if db_folder:
                                print(f"[INFO] Copying filestore to Odoo container...")
                                # Copy the entire database folder
                                docker_cp_cmd = [
                                    'docker', 'cp', 
                                    f'{db_folder}/.', 
                                    f'{ODOO_CONTAINER}:/var/lib/odoo/.local/share/Odoo/filestore/{DB_NAME}/'
                                ]
                                subprocess.run(docker_cp_cmd, check=True)
                                print(f"[INFO] Filestore copied to Odoo container successfully")
                            else:
                                print(f"[WARNING] No database folder found in {zip_file}")
                            
                            # Clean up temp directory
                            shutil.rmtree(temp_extract_dir)
                            
                        except Exception as e:
                            print(f"[ERROR] Failed to restore filestore: {e}")
                            if os.path.exists(temp_extract_dir):
                                shutil.rmtree(temp_extract_dir)
                        
                    else:
                        # Non-Docker mode
                        subprocess.run(['sudo', '-u', 'odoo', 'unzip', '-o', zip_path, '-d', FILESTORE_DIR], check=True)
                    
                print("[INFO] All filestore zip files restored successfully.")
                
        except Exception as e:
            print(f"[ERROR] Failed to restore filestore from zip files: {e}")
            
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
