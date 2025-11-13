@echo off
chcp 65001 >nul
title Зарплатный бот - Автозапчасть
color 0A

echo.
echo ========================================
echo    Зарплатный бот "Автозапчасть"
echo ========================================
echo.

REM Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python с https://www.python.org/
    pause
    exit /b 1
)

echo [1/3] Проверка Python... OK
echo.

REM Проверка и установка зависимостей
echo [2/3] Проверка зависимостей...
pip show aiogram >nul 2>&1
if errorlevel 1 (
    echo Установка aiogram...
    pip install aiogram==3.7.0 python-dotenv==1.0.0 --quiet
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить зависимости!
        pause
        exit /b 1
    )
) else (
    echo Зависимости уже установлены
)
echo.

REM Проверка наличия .env файла
if not exist ".env" (
    echo [ОШИБКА] Файл .env не найден!
    echo Создайте файл .env по примеру env_v3.example
    echo.
    pause
    exit /b 1
)

echo [3/3] Запуск бота...
echo.
echo ========================================
echo    БОТ ЗАПУЩЕН!
echo ========================================
echo.
echo Откройте Telegram и напишите /start
echo Для остановки нажмите Ctrl+C
echo.

REM Запуск бота
python app_v3.py

REM Если бот остановился
echo.
echo ========================================
echo Бот остановлен
echo ========================================
pause
