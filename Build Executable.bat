@echo off
setlocal

py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name PasswordGenerator "%~dp0password_generator.py"
if errorlevel 1 (
    echo.
    echo Build failed. Install PyInstaller with: py -3 -m pip install pyinstaller
    pause
    exit /b 1
)

echo.
echo Built: "%~dp0dist\PasswordGenerator.exe"
pause
