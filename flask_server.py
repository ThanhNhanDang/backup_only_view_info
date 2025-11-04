# -*- coding: utf-8 -*-
import builtins
import logging
from config import DB_NAME, DB_USER, DB_PASSWORD, PG_PORT, PG_CONTAINER, PG_BIN, USE_POSTGRES_DOCKER
from config import MINIO_URL, ACCESS_KEY, SECRET_KEY, BUCKET_BAK, BACKUP_DIR, FILESTORE_DIR, PASSWORD_LOGIN_UI, LOCAL_TZ
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
        print(file_name)
        file_path = os.path.join(BACKUP_DIR, file_name)
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


@app.route(f'{URL}restore/<filename>', methods=['POST'])
def restore(filename):
    if filename.endswith('.dump'):
        if USE_POSTGRES_DOCKER:
            print("Restore in docker mode")
            try:
                print("Coping file dump into container...")
                docker_cp_cmd = ['docker', 'cp', os.path.join(
                    BACKUP_DIR, filename), f'{PG_CONTAINER}:/tmp/{filename}']
                subprocess.run(docker_cp_cmd, check=True)
                restore_cmd = [
                    'docker', 'exec', '-i', PG_CONTAINER,
                    'pg_restore',
                    '-U', DB_USER,
                    '-p', str(PG_PORT),
                    '-C',
                    '-d', 'postgres',
                    f'/tmp/{filename}'
                ]
                print(
                    f"[INFO] Running restore command in Docker: {' '.join(restore_cmd)}")
                result = subprocess.run(restore_cmd, check=True)
                print("[INFO] Restore completed successfully in Docker.")
            except subprocess.CalledProcessError as e:
                print(
                    f"[ERROR] pg_restore failed: Please DROP or RENAME old database before restore.")
            except Exception as ex:
                print(f"[ERROR] Unexpected error: {ex}")
        else:
            print("Postgres is installed directly on the server, not using Docker.")
            try:
                file_path = os.path.join(BACKUP_DIR, filename)
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
                print(
                    f"[INFO] Running restore command: {' '.join(restore_cmd)}")
                result = subprocess.run(restore_cmd, check=True)
                # Nếu là file zip, giải nén filestore vào FILESTORE_DIR

                print(f"[INFO] Dump file restore completed successfully.")
            except subprocess.CalledProcessError as e:
                print(
                    f"[ERROR] pg_restore failed: Please DROP or RENAME old database before restore.")
            except Exception as ex:
                print(f"[ERROR] Unexpected error: {ex}")
        zip_path = os.path.join(BACKUP_DIR)
        try:
            zip_files = [f for f in os.listdir(
                BACKUP_DIR) if f.endswith('.zip')]
            for zip_file in zip_files:
                zip_path = os.path.join(BACKUP_DIR, zip_file)
                print(f"[INFO] Restoring filestore from: {zip_file}")
               # Giải nén file zip vào thư mục đó
                subprocess.run(['sudo', '-u', 'odoo', 'unzip', '-o', zip_path, '-d', FILESTORE_DIR], check=True)

            print("[INFO] All filestore zip files restored successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to restore filestore from zip files: {e}")
    return redirect(url_for('index'))


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
