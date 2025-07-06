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
    scheduled_post_publication, scheduled_weekly_summary)
from utils.telegram_web import send_web_message, get_chat_info

logger = logging.getLogger(__name__)

# --- Состояния пользователей ---
user_states = {}


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


def set_user_state(user_id, state):
    user_states[user_id] = state


def get_user_state(user_id):
    return user_states.get(user_id, UserState.MAIN_MENU)


# --- Admin Management Handlers ---

async def handle_admin_management_menu(event, pool, client):
    """Показывает меню управления администраторами"""
    if event.sender_id not in ADMIN_USER_IDS:
        await event.respond('У вас нет прав для выполнения этой команды.')
        return
    set_user_state(event.sender_id, UserState.ADMIN_MANAGEMENT_MENU)
    await event.respond(get_admin_management_menu_text())


async def handle_admin_command(event, pool, client):
    """Обработчик команд меню управления администраторами"""
    if event.sender_id not in ADMIN_USER_IDS:
        await event.respond('У вас нет прав для выполнения этой команды.')
        return

    command = event.text.strip()

    if command == '1':  # Список админов
        await handle_list_admins(event, pool)
    elif command == '2':  # Добавить админа
        set_user_state(event.sender_id, UserState.ADDING_ADMIN)
        await handle_add_admin(event, pool, client)
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
    """Показывает список всех администраторов"""
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
        async with client.conversation(event.sender_id, timeout=300) as conv:
            await conv.send_message(
                'Введите ID пользователя, которого нужно сделать администратором:')
            response = await conv.get_response()

            try:
                user_id = int(response.text.strip())
                await add_admin(pool, user_id)
                await conv.send_message(
                    f'Пользователь с ID `{user_id}` успешно добавлен в список администраторов.')
            except ValueError:
                await conv.send_message('Ошибка: ID должен быть числом.')
            except Exception as e:
                logger.error(f'Ошибка при добавлении администратора: {e}')
                await conv.send_message(
                    'Произошла ошибка при добавлении администратора.')
    except asyncio.TimeoutError:
        await event.respond(
            'Время ожидания истекло. Пожалуйста, попробуйте снова.')
    except Exception as e:
        logger.error(f'Ошибка в handle_add_admin: {e}')
        await event.respond('Произошла непредвиденная ошибка.')
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

        async with client.conversation(event.sender_id, timeout=300) as conv:
            await conv.send_message(
                'Выберите номер администратора для удаления:\n' +
                admins_list
            )
            response = await conv.get_response()

            try:
                index = int(response.text.strip()) - 1
                if 0 <= index < len(admins):
                    admin_id = admins[index]
                    if admin_id == event.sender_id:
                        await conv.send_message(
                            'Вы не можете удалить сами себя.')
                        return
                    await remove_admin(pool, admin_id)
                    await conv.send_message(
                        f'Пользователь с ID `{admin_id}` удален из списка администраторов.')
                else:
                    await conv.send_message('Неверный номер администратора.')
            except ValueError:
                await conv.send_message('Пожалуйста, введите число.')
    except asyncio.TimeoutError:
        await event.respond(
            'Время ожидания истекло. Пожалуйста, попробуйте снова.')
    except Exception as e:
        logger.error(f'Ошибка в handle_remove_admin: {e}')
        await event.respond('Произошла ошибка при удалении администратора.')


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
    try:
        set_user_state(event.sender_id, UserState.SETTING_THEME)
        async with client.conversation(event.sender_id, timeout=300) as conv:
            current_theme = await get_setting(pool,
                                              'weekly_theme') or 'не установлена'
            await conv.send_message(
                f'Текущая тема недели: {current_theme}.\nВведите новую тему:')
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
    finally:
        set_user_state(event.sender_id, UserState.MAIN_MENU)


async def handle_add_article(event, pool, client):
    try:
        set_user_state(event.sender_id, UserState.ADDING_ARTICLE)
        async with client.conversation(event.sender_id, timeout=300) as conv:
            await conv.send_message(
                'Отправьте URL статьи, которую хотите добавить:')
            url_message = await conv.get_response()
            url = url_message.text.strip()
            await conv.send_message(
                'Теперь введите теги через запятую (например: ai, ml, longread):')
            tags_message = await conv.get_response()
            tags = [tag.strip() for tag in tags_message.text.split(',')]
            await conv.send_message('Пытаюсь получить данные со страницы...')
            try:
                title, content = await parse_single_article_content(url)
                if not title:
                    await conv.send_message(
                        'Не удалось автоматически определить заголовок. Введите его вручную:')
                    title_message = await conv.get_response()
                    title = title_message.text.strip()
            except Exception as e:
                await conv.send_message(
                    f'Не удалось получить данные со страницы: {e}. Введите заголовок вручную:')
                title_message = await conv.get_response()
                title = title_message.text.strip()
                content = ''
            await conv.send_message(
                f'**Заголовок:** {title}\n**URL:** {url}\n**Теги:** {tags}\n\nСохранить эту статью? (Да/Нет)')
            confirmation = await conv.get_response()
            if confirmation.text.lower() in ['да', 'д', 'yes', 'y']:
                try:
                    await save_article(pool, title, url, content, 'manual',
                                       tags, datetime.datetime.utcnow())
                    await conv.send_message(
                        'Статья успешно добавлена. Запускаю генерацию эмбеддингов...')
                    await update_embeddings(pool)
                    await conv.send_message(
                        'Эмбеддинги для новой статьи созданы.')
                except Exception as e:
                    if 'duplicate key value' in str(e):
                        await conv.send_message(
                            'Эта статья уже есть в базе данных.')
                    else:
                        await conv.send_message(
                            f'Ошибка при сохранении статьи: {e}')
            else:
                await conv.send_message('Добавление статьи отменено.')
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
    except Exception as e:
        await event.respond(f'Произошла ошибка: {e}')
    finally:
        set_user_state(event.sender_id, UserState.MAIN_MENU)


async def handle_search(event, pool, client):
    try:
        set_user_state(event.sender_id, UserState.SEARCHING)
        async with client.conversation(event.sender_id, timeout=300) as conv:
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
    finally:
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
    try:
        set_user_state(event.sender_id, UserState.SUMMARY)
        async with client.conversation(event.sender_id, timeout=300) as conv:
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
    finally:
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
    Запускает полный сценарий недели:
    1. Отправляет сообщение с темой недели
    2. Планирует посты на неделю (1 в пн, 2 вт-чт, 1 пт)
    3. В конце публикует саммари по опубликованным постам
    """
    try:
        if event.sender_id not in ADMIN_USER_IDS:
            await event.respond('У вас нет прав для выполнения этой команды.')
            return

        await event.respond('🚀 Запуск полного недельного сценария...')

        # Get the current weekly theme
        theme = await get_setting(pool, 'weekly_theme')
        if not theme:
            await event.respond(
                '❌ Ошибка: Не установлена тема недели. Пожалуйста, установите тему с помощью команды /set_theme')
            return

        target_channel = TELEGRAM_CHANNEL or '@test_chanellmy'

        # 1. Send weekly theme message
        theme_message = f"📅 *Тема недели*: {theme}\n\n"
        theme_message += "На этой неделе мы будем обсуждать актуальные новости по этой теме. "
        theme_message += "Следите за нашими публикациями! 🚀"

        await event.respond('📢 Отправляю сообщение с темой недели...')
        await send_web_message(
            chat_id=target_channel,
            text=theme_message,
            parse_mode='Markdown'
        )

        # 2. Update embeddings and get articles
        await event.respond('🔄 Обновляю эмбеддинги...')
        await update_embeddings(pool)

        # 3. Find and schedule posts for the week
        await event.respond('📅 Составляю расписание постов на неделю...')

        # Get theme embedding for finding relevant articles
        from search.embeddings import generate_embedding
        from datetime import datetime, timedelta

        theme_embedding = await generate_embedding(theme)
        if not theme_embedding:
            await event.respond(
                '❌ Ошибка: Не удалось сгенерировать эмбеддинг темы')
            return

        # Ensure theme_embedding is in the correct format (list of floats)
        if isinstance(theme_embedding, str):
            # Try to convert from string representation if needed
            try:
                import ast
                theme_embedding = ast.literal_eval(theme_embedding)
                if not isinstance(theme_embedding, list):
                    raise ValueError("Embedding is not a list")
            except (ValueError, SyntaxError) as e:
                logger.error(f"Failed to parse embedding: {e}")
                await event.respond('❌ Ошибка: Неверный формат эмбеддинга')
                return

        # Convert to numpy array with float32 dtype
        import numpy as np
        try:
            embedding_array = np.array(theme_embedding, dtype=np.float32)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert embedding to float32: {e}")
            await event.respond('❌ Ошибка: Не удалось преобразовать эмбеддинг')
            return

        # Find relevant articles in Russian only
        query = """
            SELECT n.*, 1 - (ae.embedding <=> $1) as similarity
            FROM article_embeddings ae
            JOIN news n ON ae.article_id = n.link
            WHERE n.description ~* '[а-яА-ЯёЁ]'  -- Only Russian content
            ORDER BY similarity DESC
            LIMIT 8  -- 1(пн) + 2(вт) + 2(ср) + 2(чт) + 1(пт) = 8 постов
        """

        async with pool.acquire() as conn:
            # Use the numpy array directly - asyncpg will handle the conversion
            articles = await conn.fetch(query, embedding_array)

        if not articles or len(articles) < 8:
            await event.respond(
                '❌ Ошибка: Недостаточно статей для публикации (нужно минимум 8)')
            if articles:
                await event.respond(f'Найдено только {len(articles)} статей')
            return

        # Save articles to database for scheduled posting
        scheduled_posts = []
        article_index = 0

        # Monday - 1 post
        scheduled_posts.append({
            'day': 0,  # Monday (0 = Monday in isoweekday)
            'time': '12:00',
            'article': articles[article_index]
        })
        article_index += 1

        # Tuesday-Thursday - 2 posts per day
        for day in [1, 2, 3]:  # Tuesday (1) to Thursday (3)
            scheduled_posts.append({
                'day': day,
                'time': '12:00',
                'article': articles[article_index]
            })
            article_index += 1

            scheduled_posts.append({
                'day': day,
                'time': '19:00',
                'article': articles[article_index]
            })
            article_index += 1

        # Friday - 1 post
        scheduled_posts.append({
            'day': 4,  # Friday
            'time': '12:00',
            'article': articles[article_index]
        })

        # Publish all posts immediately with delays
        await event.respond('🚀 Публикую все посты...')

        # Get the target channel(s)
        channels = [target_channel]  # Use the target channel defined earlier

        try:
            for i, article in enumerate(articles, 1):
                try:
                    # Format the post with consistent styling
                    post = (
                        f"📌 *{article['title'].strip()}*\n\n"
                        f"ℹ️ {article['description'].strip()}\n\n"
                        f"🔗 [Читать статью]({article['link']})\n"
                        "#новости #аналитика"
                    )

                    # Send to all channels with error handling and retry
                    for channel in channels:
                        try:
                            await send_web_message(
                                chat_id=channel,
                                text=post,
                                parse_mode='Markdown',
                                disable_web_page_preview=True
                            )
                            # Add delay between posts to same channel (3 seconds)
                            await asyncio.sleep(3)
                        except Exception as e:
                            logger.error(f"Error sending to {channel}: {e}")
                            continue

                    # Add delay between different posts (5 seconds)
                    if i < len(articles):
                        await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Error formatting post {i}: {e}")
                    continue

            # Create and publish summary immediately with better formatting
            await event.respond("📊 Готовлю еженедельный дайджест...")

            try:
                # Create a well-formatted summary
                summary = (
                    "🌟 *ЕЖЕНЕДЕЛЬНЫЙ ДАЙДЖЕСТ НОВОСТЕЙ* 🌟\n\n"
                    f"📌 Тема недели: *{theme}*\n\n"
                    "📚 *Самые интересные материалы:*\n\n"
                )

                # Add each article with consistent formatting
                for i, article in enumerate(articles, 1):
                    article_text = (
                        f"{i}. *{article['title'].strip()}*\n"
                    )
                    if article.get('description'):
                        desc = article['description'].strip()
                        article_text += f"   {desc[:150]}{'...' if len(desc) > 150 else ''}\n"
                    article_text += f"   🔗 [Читать статью]({article['link']})\n\n"

                    # Add article to summary if it fits (Telegram limit is 4096 chars)
                    if len(summary + article_text) < 3800:  # Leave some space for footer
                        summary += article_text
                    else:
                        summary += "\n...и другие интересные материалы!"
                        break

                # Add footer with engagement
                summary += (
                    "\n💬 Какая тема была для вас самой интересной? Делитесь в комментариях!\n"
                    "🔔 Подпишитесь, чтобы не пропустить новые материалы!"
                )

                # Send summary to all channels with error handling
                for channel in channels:
                    try:
                        await send_web_message(
                            chat_id=channel,
                            text=summary,
                            parse_mode='Markdown',
                            disable_web_page_preview=True
                        )
                        await asyncio.sleep(3)  # Delay between channel sends
                    except Exception as e:
                        logger.error(
                            f"Error sending summary to {channel}: {e}")
                        continue

                await event.respond(
                    '✅ Еженедельное саммари успешно опубликовано!')

            except Exception as e:
                logger.error(f"Error creating summary: {e}")
                await event.respond(
                    f'❌ Ошибка при создании дайджеста: {str(e)[:200]}')

        except Exception as e:
            logger.error(f"Error in weekly training: {e}")
            await event.respond(f'❌ Ошибка: {str(e)[:200]}')

        await event.respond('🎉 Недельный сценарий успешно выполнен!')

    except Exception as e:
        error_msg = f'❌ Ошибка при выполнении недельного сценария: {str(e)}'
        logger.error(error_msg, exc_info=True)
        await event.respond(error_msg)
        await event.respond(
            f'Ошибка при выполнении еженедельного обучения: {e}')


async def handle_channels_menu(event, pool, client):
    """Показывает меню управления каналами"""
    if event.sender_id not in ADMIN_USER_IDS:
        await event.respond('У вас нет прав для выполнения этой команды.')
        return
    set_user_state(event.sender_id, UserState.CHANNELS_MENU)
    await event.respond(get_channels_menu_text())


async def handle_add_channel(event, pool, client):
    try:
        if event.sender_id not in ADMIN_USER_IDS:
            await event.respond('У вас нет прав для выполнения этой команды.')
            return
        set_user_state(event.sender_id, UserState.ADDING_CHANNEL)
        async with client.conversation(event.sender_id, timeout=300) as conv:
            await conv.send_message(
                'Введите username канала (например, @channel_name или https://t.me/channel_name):')
            response = await conv.get_response()
            channel = response.text.strip()
            if 't.me/' in channel:
                channel = channel.split('t.me/')[-1].split('/')[0]
            channel = channel.replace('@', '')
            await add_channel(pool, channel)
            await conv.send_message(
                f'Канал @{channel} успешно добавлен в список источников.')
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
    except Exception as e:
        await event.respond(f'Ошибка при добавлении канала: {e}')
    finally:
        set_user_state(event.sender_id, UserState.CHANNELS_MENU)


async def handle_remove_channel(event, pool, client):
    try:
        if event.sender_id not in ADMIN_USER_IDS:
            await event.respond('У вас нет прав для выполнения этой команды.')
            return
        set_user_state(event.sender_id, UserState.REMOVING_CHANNEL)
        channels = await get_channels(pool)
        if not channels:
            await event.respond('Список каналов пуст.')
            return
        channels_list = '\n'.join(
            [f'{i + 1}. @{channel}' for i, channel in enumerate(channels)])
        async with client.conversation(event.sender_id, timeout=300) as conv:
            await conv.send_message(
                f'Выберите номер канала для удаления:\n{channels_list}')
            response = await conv.get_response()
            try:
                index = int(response.text.strip()) - 1
                if 0 <= index < len(channels):
                    channel = channels[index]
                    await remove_channel(pool, channel)
                    await conv.send_message(
                        f'Канал @{channel} успешно удален.')
                else:
                    await conv.send_message('Неверный номер канала.')
            except ValueError:
                await conv.send_message('Введите число.')
    except asyncio.TimeoutError:
        await event.respond('Время ожидания истекло. Попробуйте снова.')
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
    if event.sender_id not in ADMIN_USER_IDS:
        await event.respond('У вас нет прав для выполнения этой команды.')
        return

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

        # Обработка состояний
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
