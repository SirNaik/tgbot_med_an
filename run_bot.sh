#!/bin/bash

echo "Запуск Telegram бота для интерпретации медицинских анализов..."

# Проверяем наличие .env файла
if [ -f .env ]; then
    echo "Загружаем переменные окружения из .env файла..."
    export $(cat .env | xargs)
else
    echo "Файл .env не найден. Убедитесь, что вы создали его на основе .env.example"
    exit 1
fi

# Запускаем бота
echo "Запускаем бота..."
python3 bot.py