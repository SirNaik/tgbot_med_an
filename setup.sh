#!/bin/bash

echo "Установка Telegram бота для интерпретации медицинских анализов"

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "Python3 не найден. Устанавливаем..."
    apt-get update && apt-get install -y python3 python3-pip
fi

# Устанавливаем зависимости
echo "Устанавливаем зависимости..."
pip3 install -r requirements.txt

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "Создаем шаблон .env файла..."
    cp .env.example .env
    echo "Пожалуйста, заполните .env файл вашими учетными данными:"
    echo "- TELEGRAM_BOT_TOKEN: токен вашего Telegram бота"
    echo "- GIGACHAT_CREDENTIALS: учетные данные GigaChat"
    echo "- GIGACHAT_SCOPE: область действия GigaChat"
fi

echo "Установка завершена!"
echo "Для запуска бота выполните: python3 bot.py"