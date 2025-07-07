# bot/handlers.py
import asyncio
import datetime
import os
import logging
from telethon import events
from utils.config import ADMIN_USER_IDS, TELEGRAM_CHANNEL
from bot.keyboards import (
    get_admin_menu_text,
    get_channels_menu_text,
    get_admin_management_menu_text,
    ADMIN_COMMANDS_MAP,
    CHANNEL_COMMANDS_MAP,
    ADMIN_MANAGEMENT_MAP
)
from parsers.main_parser import run_parsing
from parsers.html_parser import parse_single_article_content
from search.embeddings import update_embeddings
from search.lm_search import semantic_search
from rag.weekly_summary import create_weekly_summary
from database.db_manager import (
    set_setting, get_setting, get_db_status,
    save_article, add_channel, get_channels, remove_channel,
    get_admins, add_admin, remove_admin
)
from scheduler.jobs import (scheduled_parsing, scheduled_embedding_update,
                            scheduled_post_publication,
                            scheduled_weekly_summary, scheduled_weekly_theme)
from utils.telegram_web import send_web_message, get_chat_info

logger = logging.getLogger(__name__)

# --- Состояния пользователей ---
user_states = {}
user_data = {}  # Для хранения временных данных пользователя


class UserState:
    MAIN_MENU = "main_menu"
    CHANNELS_MENU = "channels_menu"
    ADMIN_MANAGEMENT_MENU = "admin_management_menu"
    ADDING_ADMIN = "adding_admin"
    REMOVING_ADMIN = "removing_admin"
    ADDING_CHANNEL = "adding_channel"
    REMOVING_CHANNEL = "removing_channel"
    SETTING_THEME = "setting_theme"
    ADDING_ARTICLE = "adding_article"
    SEARCHING = "searching"
    SUMMARY = "summary"
    IN_DIALOG = "in_dialog"  # Общее состояние для всех диалогов


def set_user_state(user_id, state, data=None):
    user_states[user_id] = state
    if data:
        user_data[user_id] = data
    elif user_id in user_data:
        del user_data[user_id]


def get_user_state(user_id):
    return user_states.get(user_id, UserState.MAIN_MENU)


def get_user_data(user_id):
    return user_data.get(user_id, {})


# --- Admin Management Handlers ---

async def handle_admin_management_menu(event, pool, client):
    set_user_state(event.sender_id, UserState.ADMIN_MANAGEMENT_MENU)
    await event.respond(get_admin_management_menu_text())


async def handle_admin_command(event, pool, client):
    command = event.text.strip()

    if command == '1':  # Список админов
        await handle_list_admins(event, pool)
    elif command == '2':  # Добавить админа
        set_user_state(event.sender_id, UserState.ADDING_ADMIN)
        await event.respond(
            'Введите ID пользователя, которого нужно сделать администратором:')
    elif command == '3':  # Удалить админа
        await handle_remove_admin(event, pool, client)
    elif command == '0':  # Назад
        set_user_state(event.sender_id, UserState.MAIN_MENU)
        await event.respond(get_admin_menu_text())
    else:
        await event.respond(
            'Неизвестная команда. Пожалуйста, выберите действие из меню.')
        await event.respond(get_admin_management_menu_text())


async def handle_list_admins(event, pool):
    try:
        admins = await get_admins(pool)
        if not admins:
            await event.respond('Список администраторов пуст.')
            return

        admins_list = '\n'.join([f'• `{admin_id}`' for admin_id in admins])
        await event.respond(f'**Список администраторов:**\n{admins_list}')
    except Exception as e:
        logger.error(f'Ошибка при получении списка администраторов: {e}')
        await event.respond(
            'Произошла ошибка при получении списка администраторов.')


async def handle_add_admin(event, pool, client):
    try:
        user_id = event.text.strip()
        try:
            user_id = int(user_id)
            await add_admin(pool, user_id)
            await event.respond(
                f'Пользователь с ID `{user_id}` успешно добавлен в список администраторов.')
        except ValueError:
            await event.respond('Ошибка: ID должен быть числом.')
        except Exception as e:
            logger.error(f'Ошибка при добавлении администратора: {e}')
            await event.respond(
                'Произошла ошибка при добавлении администратора.')
    finally:
        set_user_state(event.sender_id, UserState.ADMIN_MANAGEMENT_MENU)


async def handle_remove_admin(event, pool, client):
    try:
        admins = await get_admins(pool)
        if not admins:
            await event.respond('Список администраторов пуст.')
            return

        admins_list = '\n'.join(
            [f'{i + 1}. `{admin_id}`' for i, admin_id in enumerate(admins)])
        await event.respond(
            f'Выберите номер администратора для удаления:\n{admins_list}')
        set_user_state(event.sender_id, UserState.REMOVING_ADMIN,
                       {"admins": admins})
    except Exception as e:
        logger.error(f'Ошибка в handle_remove_admin: {e}')
        await event.respond('Произошла ошибка при удалении администратора.')


async def handle_remove_admin_confirm(event, pool, client):
    try:
        data = get_user_data(event.sender_id)
        admins = data.get("admins", [])

        try:
            index = int(event.text.strip()) - 1
            if 0 <= index < len(admins):
                admin_id = admins[index]
                if admin_id == event.sender_id:
                    await event.respond('Вы не можете удалить сами себя.')
                    return
                await remove_admin(pool, admin_id)
                await event.respond(
                    f'Пользователь с ID `{admin_id}` удален из списка администраторов.')
            else:
                await event.respond('Неверный номер администратора.')
        except ValueError:
            await event.respond('Пожалуйста, введите число.')
    except Exception as e:
        logger.error(f'Ошибка в handle_remove_admin_confirm: {e}')
        await event.respond('Произошла ошибка при удалении администратора.')
    finally:
        set_user_state(event.sender_id, UserState.ADMIN_MANAGEMENT_MENU)


# --- Individual Command Handlers ---

async def handle_status(event, pool):
    try:
        await event.respond('Собираю информацию о статусе системы...')
        current_theme = await get_setting(pool,
                                          'weekly_theme') or 'не установлена'
        stats = await get_db_status(pool)
        status_message = (
            f"**Статус системы**\n\n"
            f"- **Тема недели:** {current_theme}\n"
            f"- **Статей в базе:** {stats['news']}\n"
            f"- **Эмбеддингов создано:** {stats['article_embeddings']}\n"
        )
        await event.respond(status_message)
    except Exception as e:
        await event.respond(f'Ошибка при получении статуса: {e}')


async def handle_set_theme(event, pool, client):
    set_user_state(event.sender_id, UserState.SETTING_THEME)
    current_theme = await get_setting(pool, 'weekly_theme') or 'не установлена'
    await event.respond(
        f'Текущая тема недели: {current_theme}.\nВведите новую тему:')


async def handle_set_theme_confirm(event, pool, client):
    new_theme = event.text.strip()
    if not new_theme:
        await event.respond('Название темы не может быть пустым.')
        return

    await set_setting(pool, 'weekly_theme', new_theme)
    await event.respond(f'Тема недели обновлена: "{new_theme}"')
    set_user_state(event.sender_id, UserState.MAIN_MENU)


async def handle_add_article(event, pool, client):
    set_user_state(event.sender_id, UserState.ADDING_ARTICLE, {"step": "url"})
    await event.respond('Отправьте URL статьи, которую хотите добавить:')


async def handle_add_article_step(event, pool, client):
    data = get_user_data(event.sender_id)
    step = data.get("step")
    user_data = get_user_data(event.sender_id)

    if step == "url":
        url = event.text.strip()
        set_user_state(
            event.sender_id,
            UserState.ADDING_ARTICLE,
            {"step": "tags", "url": url}
        )
        await event.respond(
            'Теперь введите теги через запятую (например: ai, ml, longread):')

    elif step == "tags":
        tags = [tag.strip() for tag in event.text.split(',')]
        url = user_data.get("url")

        set_user_state(
            event.sender_id,
            UserState.ADDING_ARTICLE,
            {"step": "processing", "url": url, "tags": tags}
        )

        await event.respond('Пытаюсь получить данные со страницы...')
        try:
            title, content = await parse_single_article_content(url)
            if not title:
                set_user_state(
                    event.sender_id,
                    UserState.ADDING_ARTICLE,
                    {"step": "manual_title", "url": url, "tags": tags}
                )
                await event.respond(
                    'Не удалось автоматически определить заголовок. Введите его вручную:')
            else:
                set_user_state(
                    event.sender_id,
                    UserState.ADDING_ARTICLE,
                    {"step": "confirm", "url": url, "tags": tags,
                     "title": title, "content": content}
                )
                await event.respond(
                    f'**Заголовок:** {title}\n**URL:** {url}\n**Теги:** {tags}\n\n'
                    'Сохранить эту статью? (Да/Нет)'
                )
        except Exception as e:
            set_user_state(
                event.sender_id,
                UserState.ADDING_ARTICLE,
                {"step": "manual_title", "url": url, "tags": tags}
            )
            await event.respond(
                f'Не удалось получить данные со страницы: {e}. Введите заголовок вручную:')

    elif step == "manual_title":
        title = event.text.strip()
        url = user_data.get("url")
        tags = user_data.get("tags")

        set_user_state(
            event.sender_id,
            UserState.ADDING_ARTICLE,
            {"step": "confirm", "url": url, "tags": tags, "title": title,
             "content": ''}
        )
        await event.respond(
            f'**Заголовок:** {title}\n**URL:** {url}\n**Теги:** {tags}\n\n'
            'Сохранить эту статью? (Да/Нет)'
        )

    elif step == "confirm":
        if event.text.lower() in ['да', 'д', 'yes', 'y']:
            url = user_data.get("url")
            title = user_data.get("title")
            content = user_data.get("content", '')
            tags = user_data.get("tags")

            try:
                await save_article(pool, title, url, content, 'manual', tags,
                                   datetime.datetime.utcnow())
                await event.respond(
                    'Статья успешно добавлена. Запускаю генерацию эмбеддингов...')
                await update_embeddings(pool)
                await event.respond('Эмбеддинги для новой статьи созданы.')
            except Exception as e:
                if 'duplicate key value' in str(e):
                    await event.respond('Эта статья уже есть в базе данных.')
                else:
                    await event.respond(f'Ошибка при сохранении статьи: {e}')
        else:
            await event.respond('Добавление статьи отменено.')

        set_user_state(event.sender_id, UserState.MAIN_MENU)


async def handle_search(event, pool, client):
    set_user_state(event.sender_id, UserState.SEARCHING)
    await event.respond('Введите ваш поисковый запрос:')


async def handle_search_confirm(event, pool, client):
    query = event.text
    await event.respond(f'Ищу статьи по запросу: "{query}"...')
    results = await semantic_search(query, pool)

    if not results:
        await event.respond('Ничего не найдено.')
    else:
        response_message = "Вот что удалось найти:\n\n"
        for i, article in enumerate(results, 1):
            response_message += f"{i}. {article['title']}\n"
            response_message += f"   {article['url']}\n\n"
        await event.respond(response_message, link_preview=False)

    set_user_state(event.sender_id, UserState.MAIN_MENU)


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
    set_user_state(event.sender_id, UserState.SUMMARY)
    await event.respond('Введите тему для еженедельного саммари:')


async def handle_summary_confirm(event, pool, client):
    theme = event.text
    await event.respond(f'Создаю саммари по теме: "{theme}"...')
    summary = await create_weekly_summary(theme, pool)
    await event.respond(summary)
    set_user_state(event.sender_id, UserState.MAIN_MENU)


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
    """
    Запускает полный сценарий недели, используя существующие задачи из jobs.py:
    1. Устанавливает тему недели (scheduled_weekly_theme)
    2. Выполняет парсинг источников (scheduled_parsing)
    3. Обновляет эмбеддинги (scheduled_embedding_update)
    4. Планирует и публикует посты (scheduled_post_publication)
    5. Публикует саммари (scheduled_weekly_summary)
    """
    try:
        if event.sender_id not in ADMIN_USER_IDS:
            await event.respond('У вас нет прав для выполнения этой команды.')
            return

        await event.respond('🚀 Запуск полного недельного сценария...')

        # 1. Установка темы недели
        await event.respond('🎯 Устанавливаю тему недели...')
        try:
            await scheduled_weekly_theme(client, pool)
            theme = await get_setting(pool, 'weekly_theme')
            await event.respond(f'✅ Тема недели установлена: {theme}')
        except Exception as e:
            logger.error(f"Error setting weekly theme: {e}", exc_info=True)
            await event.respond(f'❌ Ошибка установки темы: {str(e)[:200]}')
            return

        # 2. Парсинг источников
        await event.respond('🔍 Запускаю парсинг источников...')
        try:
            await scheduled_parsing(client, pool)
            await event.respond('✅ Парсинг завершен успешно')
        except Exception as e:
            logger.error(f"Error during parsing: {e}", exc_info=True)
            await event.respond(f'❌ Ошибка парсинга: {str(e)[:200]}')
            return

        # 3. Обновление эмбеддингов
        await event.respond('🔄 Обновляю эмбеддинги...')
        try:
            await scheduled_embedding_update(pool)
            await event.respond('✅ Эмбеддинги обновлены')
        except Exception as e:
            logger.error(f"Error updating embeddings: {e}", exc_info=True)
            await event.respond(
                f'❌ Ошибка обновления эмбеддингов: {str(e)[:200]}')
            return

        # 4. Публикация тестовых постов по расписанию
        await event.respond('📅 Публикую тестовые посты...')

        # Создаем тестовое расписание (пн-пт)
        test_schedule = [
            # Понедельник
            {'day': 0, 'time': '12:00', 'type': 'morning'},
            # Вторник
            {'day': 1, 'time': '10:00', 'type': 'morning'},
            {'day': 1, 'time': '19:00', 'type': 'evening'},
            # Среда
            {'day': 2, 'time': '10:00', 'type': 'morning'},
            {'day': 2, 'time': '19:00', 'type': 'evening'},
            # Четверг
            {'day': 3, 'time': '10:00', 'type': 'morning'},
            {'day': 3, 'time': '19:00', 'type': 'evening'},
            # Пятница
            {'day': 4, 'time': '10:00', 'type': 'morning'},
            {'day': 4, 'time': '20:00', 'type': 'summary'}
        ]

        for item in test_schedule:
            try:
                if item['type'] == 'summary':
                    await event.respond(f"📊 Публикую еженедельный дайджест...")
                    await scheduled_weekly_summary(client, pool)
                else:
                    time_of_day = item['type']
                    await event.respond(
                        f"📌 Публикую {time_of_day} пост для дня {item['day']}...")
                    await scheduled_post_publication(client, pool, time_of_day)

                await asyncio.sleep(5)  # Небольшая задержка между постами
            except Exception as e:
                logger.error(f"Error publishing {item['type']} post: {e}",
                             exc_info=True)
                await event.respond(
                    f'⚠️ Ошибка публикации {item["type"]} поста: {str(e)[:200]}')
                await asyncio.sleep(5)  # Небольшая задержка между постами

        # 5. Финализация
        await event.respond('🎉 Недельный сценарий успешно выполнен!')
        logger.info("Weekly training scenario completed successfully")

    except Exception as e:
        error_msg = f'❌ Критическая ошибка в недельном сценарии: {str(e)}'
        logger.error(error_msg, exc_info=True)
        await event.respond(error_msg)


async def handle_channels_menu(event, pool, client):
    """Показывает меню управления каналами"""
    set_user_state(event.sender_id, UserState.CHANNELS_MENU)
    await event.respond(get_channels_menu_text())


async def handle_add_channel(event, pool, client):
    set_user_state(event.sender_id, UserState.ADDING_CHANNEL)
    await event.respond(
        'Введите username канала (например, @channel_name или https://t.me/channel_name):')


async def handle_add_channel_confirm(event, pool, client):
    channel = event.text.strip()
    if 't.me/' in channel:
        channel = channel.split('t.me/')[-1].split('/')[0]
    channel = channel.replace('@', '')

    try:
        await add_channel(pool, channel)
        await event.respond(
            f'Канал @{channel} успешно добавлен в список источников.')
    except Exception as e:
        await event.respond(f'Ошибка при добавлении канала: {e}')

    set_user_state(event.sender_id, UserState.CHANNELS_MENU)


async def handle_remove_channel(event, pool, client):
    try:
        channels = await get_channels(pool)
        if not channels:
            await event.respond('Список каналов пуст.')
            return

        channels_list = '\n'.join(
            [f'{i + 1}. @{channel}' for i, channel in enumerate(channels)])
        await event.respond(
            f'Выберите номер канала для удаления:\n{channels_list}')
        set_user_state(event.sender_id, UserState.REMOVING_CHANNEL,
                       {"channels": channels})
    except Exception as e:
        await event.respond(f'Ошибка при удалении канала: {e}')


async def handle_remove_channel_confirm(event, pool, client):
    try:
        data = get_user_data(event.sender_id)
        channels = data.get("channels", [])

        try:
            index = int(event.text.strip()) - 1
            if 0 <= index < len(channels):
                channel = channels[index]
                await remove_channel(pool, channel)
                await event.respond(f'Канал @{channel} успешно удален.')
            else:
                await event.respond('Неверный номер канала.')
        except ValueError:
            await event.respond('Введите число.')
    except Exception as e:
        await event.respond(f'Ошибка при удалении канала: {e}')
    finally:
        set_user_state(event.sender_id, UserState.CHANNELS_MENU)


async def handle_list_channels(event, pool):
    """Показывает список всех каналов для парсинга"""
    try:
        channels = await get_channels(pool)
        if not channels:
            await event.respond('Список каналов пуст.')
            return

        channels_list = '\n'.join([f'• @{channel}' for channel in channels])
        await event.respond(
            f'**Список отслеживаемых каналов:**\n{channels_list}')
    except Exception as e:
        logger.error(f'Ошибка при получении списка каналов: {e}')
        await event.respond('Произошла ошибка при получении списка каналов.')


async def handle_channel_command(event, pool, client):
    """Обработчик команд меню управления каналами"""
    command = event.text.strip()

    if command == '1':  # Список каналов
        await handle_list_channels(event, pool)
    elif command == '2':  # Добавить канал
        await handle_add_channel(event, pool, client)
    elif command == '3':  # Удалить канал
        await handle_remove_channel(event, pool, client)
    elif command == '0':  # Назад
        set_user_state(event.sender_id, UserState.MAIN_MENU)
        await event.respond(get_admin_menu_text())
    else:
        await event.respond(
            'Неизвестная команда. Пожалуйста, выберите действие из меню.')
        await event.respond(get_channels_menu_text())


# --- Main Handler Registration ---

async def register_handlers(client, pool):
    """Register all message handlers."""

    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        set_user_state(event.sender_id, UserState.MAIN_MENU)
        if event.sender_id in ADMIN_USER_IDS:
            await event.respond(get_admin_menu_text())
        else:
            await event.respond('Извините, у вас нет доступа к этой команде.')
        raise events.StopPropagation

    @client.on(events.NewMessage(from_users=ADMIN_USER_IDS))
    async def main_handler(event):
        current_state = get_user_state(event.sender_id)
        command = event.text.strip()

        # Обработка специальных состояний
        if current_state == UserState.ADDING_ADMIN:
            await handle_add_admin(event, pool, client)
            return

        if current_state == UserState.REMOVING_ADMIN:
            await handle_remove_admin_confirm(event, pool, client)
            return

        if current_state == UserState.SETTING_THEME:
            await handle_set_theme_confirm(event, pool, client)
            return

        if current_state == UserState.ADDING_ARTICLE:
            await handle_add_article_step(event, pool, client)
            return

        if current_state == UserState.SEARCHING:
            await handle_search_confirm(event, pool, client)
            return

        if current_state == UserState.SUMMARY:
            await handle_summary_confirm(event, pool, client)
            return

        if current_state == UserState.ADDING_CHANNEL:
            await handle_add_channel_confirm(event, pool, client)
            return

        if current_state == UserState.REMOVING_CHANNEL:
            await handle_remove_channel_confirm(event, pool, client)
            return

        # Обработка меню
        if current_state == UserState.CHANNELS_MENU:
            if command in CHANNEL_COMMANDS_MAP:
                await handle_channel_command(event, pool, client)
            else:
                await event.respond(
                    "Пожалуйста, используйте команды из текущего меню")
                await event.respond(get_channels_menu_text())
            return

        if current_state == UserState.ADMIN_MANAGEMENT_MENU:
            if command in ADMIN_MANAGEMENT_MAP:
                await handle_admin_command(event, pool, client)
            else:
                await event.respond(
                    "Пожалуйста, используйте команды из текущего меню")
                await event.respond(get_admin_management_menu_text())
            return

        # Главное меню
        if command == '/start':
            return

        if command not in ADMIN_COMMANDS_MAP:
            await event.respond(
                "Неизвестная команда. Пожалуйста, выберите действие из меню.")
            await event.respond(get_admin_menu_text())
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
        elif command_name == "Управление каналами":
            await handle_channels_menu(event, pool, client)
        elif command_name == "Управление админами":
            await handle_admin_management_menu(event, pool, client)
        elif command_name == "Назад":
            set_user_state(event.sender_id, UserState.MAIN_MENU)
            await event.respond(get_admin_menu_text())
