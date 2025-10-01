@echo off
echo Starting ChipMate Web Interface...
echo.

echo [1/3] Starting MongoDB...
start "MongoDB" cmd /k "mongod --dbpath data"
timeout /t 3 /nobreak >nul

echo [2/3] Starting Flask API Server...
cd /d "%~dp0"
start "ChipMate API" cmd /k "python src/api/web_api.py"
timeout /t 3 /nobreak >nul

echo [3/3] Starting Angular Development Server...
cd web-ui
start "ChipMate Web UI" cmd /k "npm start"

echo.
echo ========================================
echo ChipMate Web Interface Starting...
echo ========================================
echo.
echo Web Interface: http://localhost:4200
echo API Server: http://localhost:5000
echo.
echo Press any key to close this window...
pause >nul