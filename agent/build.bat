@echo off
REM ==================================================================
REM  Build agent.py thanh file .exe don le (KHONG can cai Python tren may nhan)
REM  Yeu cau mot lan:  pip install pyinstaller pynput websocket-client
REM ==================================================================

echo Dang dong goi agent thanh .exe ...

set PY_CMD=

where py >nul 2>&1
if not errorlevel 1 set PY_CMD=py -m PyInstaller

if "%PY_CMD%"=="" (
  where python >nul 2>&1
  if not errorlevel 1 set PY_CMD=python -m PyInstaller
)

if "%PY_CMD%"=="" (
  where pyinstaller >nul 2>&1
  if not errorlevel 1 set PY_CMD=pyinstaller
)

if "%PY_CMD%"=="" (
  if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set PY_CMD="%LocalAppData%\Programs\Python\Python314\python.exe" -m PyInstaller
  if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set PY_CMD="%LocalAppData%\Programs\Python\Python313\python.exe" -m PyInstaller
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set PY_CMD="%LocalAppData%\Programs\Python\Python312\python.exe" -m PyInstaller
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set PY_CMD="%LocalAppData%\Programs\Python\Python311\python.exe" -m PyInstaller
  if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set PY_CMD="%LocalAppData%\Programs\Python\Python310\python.exe" -m PyInstaller
)

if "%PY_CMD%"=="" (
  echo [!] Khong tim thay Python trong PATH hoac LocalAppData.
  echo [!] Vui long chay: py -m PyInstaller --noconfirm clickdongbo-agent.spec
  exit /b 1
)

echo Dang su dung: %PY_CMD%
%PY_CMD% --noconfirm clickdongbo-agent.spec
if errorlevel 1 (
  echo [!] Build loi. Kiem tra da cai: pip install pyinstaller
  exit /b 1
)

REM Copy config.json ra canh file exe de nguoi dung sua duoc
copy /Y config.json dist\config.json >nul 2>&1

echo.
echo ================================================================
echo  XONG! File dung duoc tai:
echo    dist\clickdongbo-agent.exe
echo    dist\config.json     (sua server / channel / name tai day)
echo.
echo  Copy ca 2 file nay sang bat ky may nao (Windows) de chay --
echo  KHONG can cai Python.
echo ================================================================

