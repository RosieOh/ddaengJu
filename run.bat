@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 포트는 여기만 고치면 됩니다.
rem 8000 은 다른 로컬 서버(Django, 다른 API)와 자주 겹쳐서 8200 을 씁니다.
set PORT=8200

echo [파워링크 노출순위 모니터] 시작합니다...
echo.

python -c "import fastapi, uvicorn, requests, pandas, openpyxl" 2>nul
if errorlevel 1 (
    echo 필요한 패키지를 설치합니다. 잠시만 기다려 주세요...
    python -m pip install -r requirements.txt
    echo.
)

echo 브라우저에서 http://localhost:%PORT% 으로 접속하세요.
echo 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.

rem 서버가 포트를 잡기 전에 브라우저가 열리면 '연결할 수 없음'이 뜬다.
rem 2초 뒤에 열도록 따로 띄워 두고, 이 창은 바로 서버를 시작한다.
start "" /min cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:%PORT%"
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%

pause
