# Định nghĩa thư mục hiện tại (tương đương SCRIPT_DIR trong Bash)
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Output "Checking for existing flask_server.py process..."

# Tìm PID của flask_server.py (tương đương ps aux | grep)
$PID = Get-Process -Name python* | Where-Object { $_.CommandLine -like "*flask_server.py*" } | Select-Object -ExpandProperty Id

if ($PID) {
    Write-Output "Flask server is running with PID: $PID"
    Write-Output "Killing process $PID..."
    Stop-Process -Id $PID -Force
} else {
    Write-Output "No existing Flask server process found."
}

# Đường dẫn đến môi trường ảo
$VENV_PATH = Join-Path $SCRIPT_DIR "venv"

# Kiểm tra Python trong môi trường ảo
$PYTHON = Join-Path $VENV_PATH "Scripts\python.exe"

if (Test-Path $PYTHON) {
    Write-Output "Using virtual environment Python: $PYTHON"
} else {
    Write-Output "Virtual environment not found at $VENV_PATH"
    exit 1
}

Write-Output "Starting Flask server..."

# Chuyển đến thư mục script và chạy Flask server
Set-Location $SCRIPT_DIR
Start-Process -FilePath $PYTHON -ArgumentList "-u", "$SCRIPT_DIR\flask_server.py" -RedirectStandardOutput "$SCRIPT_DIR\flask.log" -RedirectStandardError "$SCRIPT_DIR\flask.log" -NoNewWindow

Write-Output "Flask server restarted at port 8080 and running in background."