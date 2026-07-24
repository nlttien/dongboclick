@echo off
REM ==================================================================
REM  Build agent.py thanh file .exe don le (KHONG can cai Python tren may nhan)
REM  Yeu cau mot lan:  pip install pyinstaller pynput websocket-client
REM ==================================================================

echo Dang dong goi agent thanh .exe ...
REM Dung "python -m PyInstaller" de chay duoc ca khi pyinstaller khong nam trong PATH
python -m PyInstaller --noconfirm --onefile --console --name clickdongbo-agent agent.py
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
echo
echo  Copy ca 2 file nay sang bat ky may nao (Windows) de chay --
echo  KHONG can cai Python.
echo ================================================================
