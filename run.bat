@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [파워링크 노출순위 모니터] 시작합니다...
echo.

python -c "import fastapi, uvicorn, requests, pandas, openpyxl" 2>nul
if errorlevel 1 (
    echo 필요한 패키지를 설치합니다. 잠시만 기다려 주세요...
    python -m pip install -r requirements.txt
    echo.
)

echo 브라우저에서 http://localhost:8000 으로 접속하세요.
echo 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.

start "" http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
