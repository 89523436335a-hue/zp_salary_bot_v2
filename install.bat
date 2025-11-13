@echo off
chcp 65001 >nul
title Установка зависимостей
color 0B

echo.
echo ========================================
echo    Первая установка зависимостей
echo ========================================
echo.

REM Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo.
    echo Установите Python:
    echo 1. Перейдите на https://www.python.org/downloads/
    echo 2. Скачайте последнюю версию
    echo 3. При установке отметьте "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo Python найден:
python --version
echo.

echo Установка зависимостей...
echo.

pip install aiogram==3.7.0 python-dotenv==1.0.0

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости!
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo    УСТАНОВКА ЗАВЕРШЕНА!
echo ========================================
echo.
echo Теперь запустите start_bot.bat
echo.
pause
