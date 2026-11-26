@echo off
cd /d "%~dp0"
echo Membangun CleanGram.exe standalone (Modern WebView2 Desktop)...
py -3.13 -m PyInstaller --noconfirm --onefile --windowed --name "CleanGram" --icon "assets\icon.ico" --add-data "assets;assets" --add-data "ui;ui" --collect-all webview --collect-all clr_loader --collect-all pythonnet --exclude-module numpy --exclude-module scipy --exclude-module matplotlib --exclude-module pandas --exclude-module torch --exclude-module cv2 app.py
echo.
if exist "dist\CleanGram.exe" (
    echo BERHASIL! File siap di: desktop\dist\CleanGram.exe
) else (
    echo GAGAL membangun executable.
)
pause
