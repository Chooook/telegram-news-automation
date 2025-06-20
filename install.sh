#!/bin/bash
set -e

REPO_URL="https://github.com/pankeig/telegram-news-automation.git"
DUMP_FILE="mydb_dump.sql"

# 1. Клонирование репозитория
if [ ! -d telegram-news-automation ]; then
  echo "=== Клонируем репозиторий ==="
  git clone "$REPO_URL"
fi
cd telegram-news-automation

# 2. Проверка .env
# 2. Проверка .env
if [ ! -f .env ]; then
  echo "⚠️  Нет .env! Создайте .env вручную."
  exit 1
fi

# 3. Проверка дампа базы
if [ ! -f ../$DUMP_FILE ] && [ ! -f $DUMP_FILE ]; then
  echo "⚠️  Положите дамп вашей базы $DUMP_FILE в папку проекта или на уровень выше!"
  exit 1
fi
if [ -f ../$DUMP_FILE ]; then
  cp ../$DUMP_FILE .
fi

# 4. Запуск PostgreSQL
echo "=== Запускаем PostgreSQL в Docker ==="
docker-compose up -d db

# 5. Ждём запуска базы
sleep 10

# 6. Восстановление базы
echo "=== Восстанавливаем базу данных из дампа ==="
docker-compose exec -T db psql -U bot_user -d telegram_bot_db < $DUMP_FILE

# 7. Сборка и запуск бота
echo "=== Собираем и запускаем бота ==="
docker-compose up --build -d bot

echo "=== Всё готово! Бот и база работают в Docker! ===" 