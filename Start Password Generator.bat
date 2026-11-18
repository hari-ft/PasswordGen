@echo off
py -3 "%~dp0password_generator.py"
if errorlevel 1 (
    echo.
    echo Could not start Password Generator. Make sure Python 3 is installed.
    pause
)
