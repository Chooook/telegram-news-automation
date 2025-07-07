import logging
import random
from datetime import datetime, timedelta
from parsers.main_parser import run_parsing
from search.embeddings import update_embeddings, generate_embedding
from rag.weekly_summary import create_weekly_summary
from utils.config import TELEGRAM_CHANNEL
import httpx
from database.db_manager import (
    get_setting, set_setting, find_similar_articles,
    get_published_links, add_published_link, get_articles_by_date_range
)
from utils.telegram_web import send_web_message

logger = logging.getLogger(__name__)

async def scheduled_parsing(client, pool):
    """Job to run parsing of all sources."""
    logger.info("Scheduler: Running scheduled parsing...")
    await run_parsing(client, pool)
    logger.info("Scheduler: Scheduled parsing finished.")

async def scheduled_embedding_update(pool):
    """Job to update embeddings for new articles."""
    logger.info("Scheduler: Running scheduled embedding update...")
    await update_embeddings(pool)
    logger.info("Scheduler: Scheduled embedding update finished.")

WEEKLY_THEMES = [
    {
        "title": "🤖 Машинное обучение",
        "description": "Исследуем последние достижения в области машинного обучения и нейронных сетей."
    },
    {
        "title": "📊 Обработка данных",
        "description": "Все о сборе, обработке и анализе больших объемов данных."
    },
    {
        "title": "🧠 Искусственный интеллект",
        "description": "Новости и исследования в области искусственного интеллекта."
    },
    {
        "title": "🔍 Компьютерное зрение",
        "description": "Анализ изображений, распознавание объектов и другие технологии компьютерного зрения."
    },
    {
        "title": "💬 Обработка естественного языка",
        "description": "NLP, чат-боты, машинный перевод и другие языковые технологии."
    },
    {
        "title": "⚡️ Генеративные модели",
        "description": "DALL-E, GPT и другие генеративные модели, меняющие наше представление о творчестве."
    },
    {
        "title": "🤝 ИИ в бизнесе",
        "description": "Как искусственный интеллект трансформирует современный бизнес."
    },
    {
        "title": "🔮 Будущее технологий",
        "description": "Технологические тренды и прогнозы на ближайшее будущее."
    }
]

async def set_weekly_theme(pool):
    """Set a new random weekly theme with description and hashtags."""
    try:
        # Get the last used theme indices to avoid repetition
        last_theme_indices = await get_setting(pool, 'last_theme_indices')
        last_theme_indices = [int(x) for x in last_theme_indices.split(',')] if last_theme_indices else []

        # Get available theme indices
        available_indices = [i for i in range(len(WEEKLY_THEMES)) if i not in last_theme_indices]

        # If all themes were used, reset
        if not available_indices:
            available_indices = list(range(len(WEEKLY_THEMES)))
            last_theme_indices = []

        # Select random theme
        theme_index = random.choice(available_indices)
        theme = WEEKLY_THEMES[theme_index]

        # Update last theme indices (keep last 3)
        new_last_indices = [str(theme_index)] + [str(i) for i in last_theme_indices[:2]]
        await set_setting(pool, 'last_theme_indices', ','.join(new_last_indices))

        # Save current theme
        await set_setting(pool, 'weekly_theme', theme['title'])
        await set_setting(pool, 'weekly_theme_description', theme['description'])

        # Generate relevant hashtags based on theme
        hashtags = {
            '🤖 Машинное обучение': '#МашинноеОбучение #НейронныеСети #AI',
            '📊 Обработка данных': '#АнализДанных #BigData #DataScience',
            '🧠 Искусственный интеллект': '#ИИ #ИскусственныйИнтеллект #AI',
            '🔍 Компьютерное зрение': '#ComputerVision #РаспознаваниеОбразов',
            '💬 Обработка естественного языка': '#NLP #ЧатБоты #ЯзыковыеМодели',
            '⚡️ Генеративные модели': '#ГенеративныеМодели #DALLE #GPT',
            '🤝 ИИ в бизнесе': '#ИИвБизнесе #Технологии #Инновации',
            '🔮 Будущее технологий': '#ТехнологииБудущего #Тренды2024'
        }.get(theme['title'], '#ИИ #Технологии #Наука')

        # Create engaging announcement
        emojis = ['🚀', '🌟', '🔍', '📚', '🧠', '💡', '🎯', '📈']
        emoji = random.choice(emojis)

        announcement = (
            f"{emoji} *{theme['title']}* {emoji}\n\n"
            f"{theme['description']}\n\n"
            f"📅 *План на неделю:*\n"
            f"• Вт-Чт: Утренние и вечерние посты по теме\n"
            f"• Пт: Итоговый дайджест недели\n\n"
            f"{hashtags}"
        )

        logger.info(f"Set new weekly theme: {theme['title']}")
        return theme['title'], announcement

    except Exception as e:
        logger.error(f"Error setting weekly theme: {e}", exc_info=True)
        # Fallback to default theme
        default_theme = "🤖 Искусственный интеллект"
        await set_setting(pool, 'weekly_theme', default_theme)
        return default_theme, f"🎯 Новая тема недели: {default_theme}"

async def scheduled_weekly_theme(client, pool):
    """Job to set new weekly theme on Monday 9:00."""
    logger.info("Scheduler: Setting new weekly theme...")

    try:
        theme, announcement = await set_weekly_theme(pool)
        logger.info(f"Scheduler: New weekly theme set to '{theme}'")

        # Generate a more detailed theme description
        from rag.llm_utils import generate_theme_description
        theme_desc = await generate_theme_description(theme)

        # Format the announcement with the generated description
        formatted_announcement = (
            f"🎯 *Новая тема недели: {theme}*\n\n"
            f"{theme_desc}\n\n"
            "В течение недели будем публиковать интересные материалы по этой теме. "
            "Не пропустите важные обновления!"
        )

        # Send announcement to channel
        success = await send_web_message(
            chat_id=TELEGRAM_CHANNEL,
            text=formatted_announcement,
            parse_mode='Markdown'
        )

        if not success:
            logger.error("Scheduler: Failed to send theme announcement")

    except Exception as e:
        logger.error(f"Scheduler: Error setting weekly theme: {e}", exc_info=True)
        # Try to send at least a simple message if the detailed one fails
        try:
            await send_web_message(
                chat_id=TELEGRAM_CHANNEL,
                text=f"🎯 *Новая тема недели: {theme}*\n\n"
                     "Следите за нашими публикациями в течение недели!",
                parse_mode='Markdown'
            )
        except Exception as e2:
            logger.error(f"Scheduler: Failed to send fallback theme announcement: {e2}")

async def publish_scheduled_post(pool, client):
    """Publish the next scheduled post for today."""
    try:
        # Get current day and time
        now = datetime.now()
        current_day = now.weekday()  # 0 = Monday, 6 = Sunday
        current_time = now.strftime('%H:%M')

        # Get scheduled posts
        scheduled_posts = await get_setting(pool, 'scheduled_posts')
        if not scheduled_posts:
            logger.warning("No scheduled posts found")
            return False

        scheduled_posts = eval(scheduled_posts)  # Convert string back to list

        # Find posts for current day and time
        posts_to_publish = [
            p for p in scheduled_posts
            if p['day'] == current_day and p['time'] == current_time
        ]

        if not posts_to_publish:
            logger.info(f"No posts scheduled for {current_day} at {current_time}")
            return False

        # Publish all matching posts
        for post in posts_to_publish:
            article = post['article']
            post_text = f"*{article['title']}*\n\n"
            if article.get('description'):
                post_text += f"{article['description']}\n\n"
            post_text += f"🔗 {article['link']}"

            await send_web_message(
                chat_id=TELEGRAM_CHANNEL,
                text=post_text,
                parse_mode='Markdown'
            )

            # Mark as published
            scheduled_posts.remove(post)
            await set_setting(pool, 'scheduled_posts', str(scheduled_posts))

        return True

    except Exception as e:
        logger.error(f"Error publishing scheduled post: {e}", exc_info=True)
        return False

async def scheduled_weekly_summary(client, pool):
    """Job to create and post a weekly summary on Friday 20:00."""
    logger.info("Scheduler: Generating weekly summary...")

    try:
        # Calculate start and end of the current week (Monday to Sunday)
        now = datetime.now()
        start_of_week = now - timedelta(days=now.weekday())  # Monday
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0,
                                              microsecond=0)
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        end_of_week = end_of_week.replace(hour=23, minute=59, second=59,
                                          microsecond=999999)

        # 1. Get scheduled posts to exclude them
        scheduled_posts = await get_setting(pool, 'scheduled_posts')
        if scheduled_posts:
            scheduled_posts = eval(scheduled_posts)
            scheduled_links = {p['article']['link'] for p in scheduled_posts}
        else:
            scheduled_links = set()
            logger.info("No scheduled posts found")

        # 2. Get all articles from this week
        weekly_articles = await get_articles_by_date_range(pool, start_of_week,
                                                           end_of_week)
        if not weekly_articles:
            logger.warning("Scheduler: No articles found for the week")
            return

        # 3. Get actually published articles
        published_links = await get_published_links(pool)
        if not published_links:
            logger.warning("No published articles found for weekly summary")
            return

        # 4. Combined filtering:
        # - must be published (in published_links)
        # - must not be scheduled (not in scheduled_links)
        final_articles = [
            a for a in weekly_articles
            if
            a['link'] in published_links and a['link'] not in scheduled_links
        ]

        if not final_articles:
            logger.warning(
                "No articles available for weekly summary after filtering")
            return

        # Get theme
        theme = await get_setting(pool, 'weekly_theme') or "Актуальные новости"

        logger.info(
            f"Creating weekly summary for theme '{theme}' ({len(final_articles)} articles)...")
        summary = await create_weekly_summary(theme, pool, final_articles)

        if not summary:
            logger.error("Failed to generate weekly summary content")
            return

        formatted_summary = (
            f"📊 *Итоги недели: {theme}*\n\n"
            f"{summary}\n\n"
            f"Спасибо, что были с нами на этой неделе!"
        )

        logger.info(
            f"Posting weekly summary ({len(formatted_summary)} chars)...")
        success = await send_web_message(
            chat_id=TELEGRAM_CHANNEL,
            text=formatted_summary,
            parse_mode='Markdown'
        )

        if not success:
            logger.error("Failed to post weekly summary to Telegram")

    except Exception as e:
        logger.error(f"Error in weekly summary generation: {e}", exc_info=True)
        raise

async def publish_article(article, pool):
    """Helper function to publish a single article."""
    try:
        # Check if article should be excluded
        from rag.llm_utils import should_exclude_article, generate_article_summary

        if should_exclude_article(article):
            logger.info(f"Skipping article (excluded by filters): {article.get('title', 'No title')}")
            return False

        # Clean HTML tags from title and description
        import re

        def clean_html(text):
            if not text:
                return ""
            # Remove HTML tags
            clean_text = re.sub(r'<[^>]+>', '', text)
            # Decode HTML entities
            import html
            clean_text = html.unescape(clean_text)
            return clean_text.strip()

        # Clean title and description
        clean_title = clean_html(article['title'])
        clean_description = clean_html(article.get('description', ''))

        # Generate a short summary of the article
        summary = await generate_article_summary({
            'title': clean_title,
            'description': clean_description,
            'link': article.get('link', '')
        })

        # Format message with title, summary and link
        message = (
            f"📌 *{clean_title}*\n\n"
            f"{summary}\n\n"
            f"🔗 [Читать статью]({article['link']})"
        )

        # Add source if available
        if article.get('source'):
            message += f"\n\n📌 Источник: {article['source']}"

        # Add hashtags based on theme
        current_theme = await get_setting(pool, 'weekly_theme')
        hashtags = {
            '🤖 Машинное обучение': '#МашинноеОбучение #НейронныеСети #AI',
            '📊 Обработка данных': '#АнализДанных #BigData #DataScience',
            '🧠 Искусственный интеллект': '#ИИ #ИскусственныйИнтеллект #AI',
            '🔍 Компьютерное зрение': '#ComputerVision #РаспознаваниеОбразов',
            '💬 Обработка естественного языка': '#NLP #ЧатБоты #ЯзыковыеМодели',
            '⚡️ Генеративные модели': '#ГенеративныеМодели #DALLE #GPT',
            '🤝 ИИ в бизнесе': '#ИИвБизнесе #Технологии #Инновации',
            '🔮 Будущее технологий': '#ТехнологииБудущего #Тренды2024'
        }.get(current_theme, '#новости #аналитика')

        message += f"\n\n{hashtags}"

        # Send message to channel
        success = await send_web_message(
            chat_id=TELEGRAM_CHANNEL,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

        if success:
            await add_published_link(pool, article['link'])
            logger.info(f"Scheduler: Successfully published post: {article['link']}")
            return True
        else:
            logger.error(f"Scheduler: Failed to publish post: {article['link']}")
            return False

    except Exception as e:
        logger.error(f"Scheduler: Error publishing article: {e}", exc_info=True)
        return False

async def scheduled_post_publication(client, pool, time_of_day=None):
    """
    Job to publish relevant articles based on the weekly theme.

    Args:
        time_of_day: 'morning' or 'evening' to select which post to publish
    """
    logger.info(f"Scheduler: Running scheduled post publication ({time_of_day or 'unspecified time'})")

    try:
        # Get current theme and its description
        theme = await get_setting(pool, 'weekly_theme')
        theme_desc = await get_setting(pool, 'weekly_theme_description')

        if not theme:
            logger.warning("Scheduler: No weekly theme set. Skipping post publication.")
            return

        # Generate embedding for the theme
        theme_embedding = await generate_embedding(theme)
        if not theme_embedding:
            logger.error("Scheduler: Failed to generate theme embedding")
            return

        # Find relevant articles (increase limit to get more variety)
        articles = await find_similar_articles(pool, theme_embedding, limit=15)
        if not articles:
            logger.warning("Scheduler: No relevant articles found for the theme")
            return

        # Filter out already published articles
        published_links = await get_published_links(pool)
        new_articles = [a for a in articles if a['link'] not in published_links]

        if not new_articles:
            logger.info("Scheduler: No new articles to publish")
            return

        # Get current day of week (0=Monday, 6=Sunday)
        day_of_week = datetime.now().weekday()

        # Select and format article based on time of day and day of week
        if time_of_day == 'morning':
            # Morning post: More technical/in-depth
            article = new_articles[0]

            # Add different intros based on day of week
            day_intros = [
                "🔥 Начало недели — время для вдохновения!",
                "📚 Вторник — отличный день для обучения!",
                "🧠 Среда — середина недели, время развиваться!",
                "💡 Четверг — идеальный момент для новых знаний!",
                "🚀 Пятница — готовимся к итогам недели!",
                "🌟 Суббота — учимся даже в выходные!",
                "🌞 Воскресенье — время для саморазвития!"
            ]

            intro = f"{day_intros[day_of_week]}\n\n"
            message = (
                f"{intro}"
                f"📌 *{theme}*\n"
                f"{theme_desc}\n\n"
                f"🔍 *{article['title']}*\n"
                f"{article.get('description', '')}\n\n"
                f"📖 Читать полностью: {article['link']}"
            )

        else:  # Evening post
            # Evening post: More engaging/entertaining
            # Select from top 5 most relevant articles
            article = random.choice(new_articles[:min(5, len(new_articles))])

            # Different formats for different days
            if day_of_week in [0, 2, 4]:  # Mon, Wed, Fri
                message = (
                    f"🌙 Вечерний дайджест по теме *{theme}*\n\n"
                    f"{random.choice(['Сегодня мы нашли для вас интересный материал:', 'Рекомендуем к прочтению:', 'Что нового в этой теме?'])}"
                    f"\n\n*{article['title']}*\n"
                    f"{article.get('description', '')}\n\n"
                    f"🔗 {article['link']}\n\n"
                    f"💬 Обсудим в комментариях?"
                )
            else:  # Tue, Thu, Sat, Sun
                # Add a question to engage audience
                questions = [
                    "Как вы думаете, как это изменит наше будущее?",
                    "Применяли ли вы подобные технологии на практике?",
                    "Что вас удивило больше всего в этом материале?",
                    "Какие аспекты темы вам хотелось бы изучить подробнее?"
                ]

                message = (
                    f"✨ *{article['title']}*\n\n"
                    f"{article.get('description', '')}\n\n"
                    f"{random.choice(questions)}\n\n"
                    f"📌 Тема недели: {theme}\n"
                    f"🔗 {article['link']}"
                )

        # Add hashtags based on theme
        hashtags = {
            '🤖 Машинное обучение': '#ML #ИИ #МашинноеОбучение #Нейросети',
            '📊 Обработка данных': '#DataScience #BigData #Аналитика',
            '🧠 Искусственный интеллект': '#ИИ #AI #ИскусственныйИнтеллект',
            '🔍 Компьютерное зрение': '#ComputerVision #CV #КомпьютерноеЗрение',
            '💬 Обработка естественного языка': '#NLP #ЧатБоты #ЯзыковыеМодели',
            '⚡️ Генеративные модели': '#ГенеративныеМодели #DALLE #GPT',
            '🤝 ИИ в бизнесе': '#ИИвБизнесе #Технологии #Стартапы',
            '🔮 Будущее технологий': '#ТехнологииБудущего #Инновации #Тренды2024'
        }.get(theme, '#ИИ #Технологии #Наука')

        # Add random emoji and hashtags
        emojis = ['💡', '🚀', '🔍', '📚', '🧠', '🎯', '📈', '🤖']
        message += f"\n\n{random.choice(emojis)} {hashtags}"

        # Send to channel
        success = await send_web_message(
            chat_id=TELEGRAM_CHANNEL,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=False
        )

        if success:
            # Mark as published
            await add_published_link(pool, article['link'])
            logger.info(f"Scheduler: Published article: {article['title']}")
            return True
        else:
            logger.error("Scheduler: Failed to publish article")
            raise RuntimeError("Scheduler: Failed to publish article")

    except Exception as e:
        logger.error(f"Scheduler: Error during post publication: {e}", exc_info=True)
        return False
