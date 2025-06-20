import asyncio
import datetime
import os
from telethon import events
from utils.config import ADMIN_USER_IDS
from bot.keyboards import get_admin_menu_text, ADMIN_COMMANDS_MAP
from parsers.main_parser import run_parsing
from parsers.html_parser import parse_single_article_content
from search.embeddings import update_embeddings
from search.lm_search import semantic_search
from rag.weekly_summary import create_weekly_summary
from database.db_manager import (
    set_setting, get_setting, get_db_status,
    save_article
)
from scheduler.jobs import scheduled_parsing, scheduled_embedding_update, scheduled_post_publication, scheduled_weekly_summary

# --- Individual Command Handlers ---

# bot/handlers.py
async def handle_status(event, pool):
    try:
        await event.respond('Собираю информацию о статусе системы...')
        current_theme = await get_setting(pool, 'weekly_theme') or 'не установлена'
        stats = await get_db_status(pool)
        status_message = (
            f"**Статус системы**\n\n"
            f"- **Тема недели:** {current_theme}\n"
            f"- **Статей в базе:** {stats['news']}\n"  # Изменено с 'articles' на 'news'
            f"- **Эмбеддингов создано:** {stats['article_embeddings']}\n"
        )
        await event.respond(status_message)
    except Exception as e:
        await event.respond(f'Ошибка при получении статуса: {e}')

async def handle_set_theme(event, pool, client):
    try:
        async with client.conversation(event.sender_id, timeout=60) as conv:
            current_theme = await get_setting(pool, 'weekly_theme') or 'не установлена'
            await conv.send_message(f'Текущая тема недели: {current_theme}.\nВведите новую тему:')
            response = await conv.get_response()
            new_theme = response.text.strip()
            if not new_theme:
                await conv.send_message('Название темы не может быть пустым.')
                return
            await set_setting(pool, 'weekly_theme', new_theme)
            await conv.send_message(f'Тема недели обновлена: "{new_theme}"')
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
    except Exception as e:
        await event.respond(f'Ошибка при установке темы: {e}')



async def handle_add_article(event, pool, client):
    try:
        async with client.conversation(event.sender_id, timeout=300) as conv:
            await conv.send_message('Отправьте URL статьи, которую хотите добавить:')
            url_message = await conv.get_response()
            url = url_message.text.strip()

            await conv.send_message('Теперь введите теги через запятую (например: ai, ml, longread):')
            tags_message = await conv.get_response()
            tags = [tag.strip() for tag in tags_message.text.split(',')]

            await conv.send_message('Пытаюсь получить данные со страницы...')
            try:
                title, content = await parse_single_article_content(url)
                if not title:
                    await conv.send_message('Не удалось автоматически определить заголовок. Введите его вручную:')
                    title_message = await conv.get_response()
                    title = title_message.text.strip()
            except Exception as e:
                await conv.send_message(f'Не удалось получить данные со страницы: {e}. Введите заголовок вручную:')
                title_message = await conv.get_response()
                title = title_message.text.strip()
                content = ''

            await conv.send_message(f'**Заголовок:** {title}\n**URL:** {url}\n**Теги:** {tags}\n\nСохранить эту статью? (Да/Нет)')
            confirmation = await conv.get_response()
            if confirmation.text.lower() == 'да':
                try:
                    await save_article(pool, title, url, content, 'manual', tags, datetime.datetime.now())
                    await conv.send_message('Статья успешно добавлена. Запускаю генерацию эмбеддингов...')
                    await update_embeddings(pool)
                    await conv.send_message('Эмбеддинги для новой статьи созданы.')
                except Exception as e:
                    if 'duplicate key value' in str(e):
                        await conv.send_message('Эта статья уже есть в базе данных.')
                    else:
                        await conv.send_message(f'Ошибка при сохранении статьи: {e}')
            else:
                await conv.send_message('Добавление статьи отменено.')
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
    except Exception as e:
        await event.respond(f'Произошла ошибка: {e}')

async def handle_search(event, pool, client):
    try:
        async with client.conversation(event.sender_id, timeout=60) as conv:
            await conv.send_message('Введите ваш поисковый запрос:')
            response = await conv.get_response()
            query = response.text
            await conv.send_message(f'Ищу статьи по запросу: "{query}"...')
            results = await semantic_search(query, pool)
            if not results:
                await conv.send_message('Ничего не найдено.')
                return
            response_message = "Вот что удалось найти:\n\n"
            for i, article in enumerate(results, 1):
                response_message += f"{i}. {article['title']}\n"
                response_message += f"   {article['url']}\n\n"
            await conv.send_message(response_message, link_preview=False)
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
    except Exception as e:
        await event.respond(f'Ошибка во время поиска: {e}')

async def handle_parsing(event, pool, client):
    await event.respond('Запускаю парсинг...')
    try:
        await run_parsing(client, pool)
        await event.respond('Парсинг завершен.')
    except Exception as e:
        await event.respond(f'Ошибка во время парсинга: {e}')

async def handle_embeddings(event, pool):
    await event.respond('Запускаю генерацию эмбеддингов...')
    try:
        await update_embeddings(pool)
        await event.respond('Генерация эмбеддингов завершена.')
    except Exception as e:
        await event.respond(f'Ошибка во время генерации эмбеддингов: {e}')

async def handle_summary(event, pool, client):
    try:
        async with client.conversation(event.sender_id, timeout=60) as conv:
            await conv.send_message('Введите тему для еженедельного саммари:')
            response = await conv.get_response()
            theme = response.text
            await conv.send_message(f'Создаю саммари по теме: "{theme}"...')
            summary = await create_weekly_summary(theme, pool)
            await conv.send_message(summary)
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
    except Exception as e:
        await event.respond(f'Ошибка во время создания саммари: {e}')

async def handle_db_status(event, pool):
    try:
        await event.respond('Получаю статистику базы данных...')
        stats = await get_db_status(pool)
        stats_message = "**Состояние базы данных:**\n\n"
        for table, count in stats.items():
            stats_message += f"- **{table.replace('_', ' ').capitalize()}:** {count}\n"
        await event.respond(stats_message)
    except Exception as e:
        await event.respond(f'Ошибка при получении состояния базы: {e}')

async def handle_view_logs(event):
    try:
        log_file = 'app.log'
        if not os.path.exists(log_file):
            await event.respond('Файл логов `app.log` еще не создан.')
            return
        await event.respond('Получаю последние 50 записей из лога...')
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        last_lines = lines[-50:]
        if not last_lines:
            await event.respond('Файл логов пуст.')
            return
        log_content = "".join(last_lines)
        if len(log_content) > 4000:
            log_content = "...\n" + log_content[-4000:]
        response_message = f"**Последние записи в `app.log`:**\n\n```{log_content}```"
        await event.respond(response_message, parse_mode='md')
    except Exception as e:
        await event.respond(f'Ошибка при просмотре логов: {e}')

async def handle_weekly_training(event, pool, client):
    try:
        await event.respond('Запускаю тренировку недельного сценария...')
        # 1. Установка темы недели
        themes = ["LLM", "Data Engineering", "Machine Learning", "AI", "Big Data"]
        import random
        theme = random.choice(themes)
        await set_setting(pool, 'weekly_theme', theme)
        await event.respond(f'Тема недели установлена: {theme}')
        # 2. Формирование пула статей (парсинг и эмбеддинги)
        await scheduled_parsing(client, pool)
        await event.respond('Парсинг завершён.')
        await scheduled_embedding_update(pool)
        await event.respond('Эмбеддинги обновлены.')
        # 3. Публикация 4 статей (имитация 2 в день, 2 дня)
        for i in range(4):
            await scheduled_post_publication(client, pool)
            await event.respond(f'Пост {i+1} опубликован.')
        # 4. Генерация и публикация саммари
        await scheduled_weekly_summary(client, pool)
        await event.respond('Еженедельное саммари опубликовано.')
        await event.respond('Тренировка недельного сценария завершена!')
    except Exception as e:
        await event.respond(f'Ошибка во время тренировки сценария: {e}')

# --- Main Handler Registration ---

async def register_handlers(client, pool):
    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        if event.sender_id not in ADMIN_USER_IDS:
            await event.respond('У вас нет прав доступа к этой команде.')
            return
        menu_text = get_admin_menu_text()
        await event.respond(menu_text, buttons=None)

    @client.on(events.NewMessage(from_users=ADMIN_USER_IDS))
    async def main_admin_handler(event):
        command = event.text.strip()

        if command == '/start':
            return
            
        if command not in ADMIN_COMMANDS_MAP:
            return

        command_name = ADMIN_COMMANDS_MAP[command]
        
        if command_name == "Статус":
            await handle_status(event, pool)
        elif command_name == "Задать тему недели":
            await handle_set_theme(event, pool, client)

        elif command_name == "Добавить статью":
            await handle_add_article(event, pool, client)
        elif command_name == "Поиск":
            await handle_search(event, pool, client)
        elif command_name == "Запустить парсинг":
            await handle_parsing(event, pool, client)
        elif command_name == "Генерация эмбеддингов":
            await handle_embeddings(event, pool)
        elif command_name == "Создать саммари":
            await handle_summary(event, pool, client)
        elif command_name == "Состояние базы":
            await handle_db_status(event, pool)
        elif command_name == "Просмотр логов":
            await handle_view_logs(event)
        elif command_name == "Тренировка недельного сценария":
            await handle_weekly_training(event, pool, client)
        
        await asyncio.sleep(1)
        menu_text = get_admin_menu_text()
        await event.respond(menu_text)
