@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 포트는 여기만 고치면 됩니다.
rem 8000 은 다른 로컬 서버(Django, 다른 API)와 자주 겹쳐서 8200 을 씁니다.
set PORT=8200

rem 가상환경은 프로젝트 안에 둔다. 전역 파이썬을 건드리지 않으므로
rem 이 PC 의 다른 파이썬 프로젝트와 패키지 버전이 충돌하지 않는다.
set VENV=.venv
set PY=%VENV%\Scripts\python.exe

echo [파워링크 노출순위 모니터] 시작합니다...
echo.

rem ── 1. 파이썬 찾기 ──────────────────────────────────────────────
rem py 런처를 먼저 본다. PATH 의 python 은 Microsoft Store 스텁일 수 있고,
rem 그 경우 실행하면 스토어 창만 열리고 아무것도 설치되지 않는다.
set BOOT=
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set BOOT=py -3
if not defined BOOT (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set BOOT=python
)
if not defined BOOT goto NOPYTHON

rem ── 2. 가상환경 (없을 때만 만든다) ──────────────────────────────
if exist "%PY%" (
    echo [1/2] 가상환경 확인됨 - 건너뜁니다.
) else (
    echo [1/2] 가상환경을 만듭니다. 처음 한 번만 걸립니다...
    %BOOT% -m venv "%VENV%"
    if errorlevel 1 goto VENVFAIL
    if not exist "%PY%" goto VENVFAIL
    echo       만들었습니다: %VENV%
)

rem ── 3. 패키지 (없을 때만 설치한다) ──────────────────────────────
rem 실제로 import 해 보는 것이 가장 확실하다. pip list 파싱은 버전 표기와
rem 배포판 이름이 달라 어긋나는 경우가 있다.
"%PY%" -c "import fastapi, uvicorn, requests, pandas, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo [2/2] 필요한 패키지를 설치합니다. 처음에는 몇 분 걸릴 수 있습니다...
    "%PY%" -m pip install --upgrade pip >nul 2>nul
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 goto PIPFAIL
    rem 설치가 끝났다고 끝난 게 아니다. 실제로 import 되는지 다시 확인한다.
    "%PY%" -c "import fastapi, uvicorn, requests, pandas, openpyxl" >nul 2>nul
    if errorlevel 1 goto PIPFAIL
    echo       설치를 마쳤습니다.
) else (
    echo [2/2] 패키지 확인됨 - 건너뜁니다.
)

echo.
echo 브라우저에서 http://localhost:%PORT% 으로 접속하세요.
echo 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.

rem 서버가 뜨기 전에 브라우저가 열리면 '연결할 수 없음'이 뜬다.
rem 2초 뒤에 열도록 따로 띄워 두고, 이 창은 바로 서버를 시작한다.
start "" /min cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:%PORT%"
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%

pause
exit /b 0

rem ── 실패했을 때 무엇을 해야 하는지 알려 주고 멈춘다 ─────────────
:NOPYTHON
echo.
echo [오류] 파이썬을 찾을 수 없습니다.
echo.
echo   https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요.
echo   설치 화면 맨 아래 'Add python.exe to PATH' 를 체크해야 합니다.
echo.
pause
exit /b 1

:VENVFAIL
echo.
echo [오류] 가상환경을 만들지 못했습니다.
echo.
echo   %VENV% 폴더를 지우고 다시 실행해 보세요.
echo   그래도 안 되면 파이썬을 다시 설치해야 할 수 있습니다.
echo.
pause
exit /b 1

:PIPFAIL
echo.
echo [오류] 패키지 설치에 실패했습니다.
echo.
echo   인터넷 연결을 확인하고 다시 실행하세요.
echo   계속 실패하면 %VENV% 폴더를 지운 뒤 다시 실행하면 처음부터 받습니다.
echo.
pause
exit /b 1
