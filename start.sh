#!/bin/bash

# Запускаем бота в фоновом режиме
python bot.py &

# Сохраняем PID процесса бота
BOT_PID=$!

# Функция для очистки
cleanup() {
    echo "Остановка бота..."
    kill $BOT_PID
    exit 0
}

# Перехватываем сигналы завершения
trap cleanup SIGINT SIGTERM

# Бесконечный цикл чтобы контейнер не завершался
while true; do
    sleep 60
done
