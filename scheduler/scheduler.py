from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .jobs import (
    scheduled_parsing,
    scheduled_embedding_update,
    scheduled_weekly_summary,
    scheduled_post_publication,
    scheduled_weekly_theme,
    publish_scheduled_post
)


def setup_scheduler(client, pool):
    """
    Initializes and configures the scheduler with the weekly workflow.
    """
    scheduler = AsyncIOScheduler(
        timezone='Europe/Moscow')  # Установка общего часового пояса

    # 1. Content Collection and Processing
    scheduler.add_job(
        scheduled_parsing,
        'interval',
        hours=4,
        args=[client, pool],
        id='parsing_job',
        name='Content Parsing',
        replace_existing=True,
        misfire_grace_time=300
    )
    scheduler.add_job(
        scheduled_embedding_update,
        'interval',
        hours=4,
        minutes=5,  # Run 5 mins after parsing job
        args=[pool],
        id='embedding_job',
        name='Update Embeddings',
        replace_existing=True,
        misfire_grace_time=300
    )

    # 2. Weekly Theme and Content Schedule
    scheduler.add_job(
        scheduled_weekly_theme,
        'cron',
        day_of_week='mon',
        hour=9,
        minute=0,
        args=[client, pool],
        id='weekly_theme_job',
        name='Set Weekly Theme',
        replace_existing=True
    )

    # Утренние посты (10:00 Вт-Пт, 12:00 Вт-Чт)
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-fri',
        hour=10,
        minute=0,
        args=[client, pool, 'morning'],
        id='morning_post_10am_job',
        name='Morning Post (10:00)',
        replace_existing=True
    )
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-thu',
        hour=12,
        minute=0,
        args=[client, pool, 'morning'],
        id='morning_post_12pm_job',
        name='Morning Post (12:00)',
        replace_existing=True
    )

    # Вечерние посты (19:00 Вт-Пт)
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-fri',
        hour=19,
        minute=0,
        args=[client, pool, 'evening'],
        id='evening_post_job',
        name='Evening Post',
        replace_existing=True
    )

    # Пятничные посты (12:00)
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='fri',
        hour=12,
        minute=0,
        args=[client, pool, 'morning'],
        id='friday_post_job',
        name='Friday Post',
        replace_existing=True
    )

    # Еженедельные итоги (20:00 Пт)
    scheduler.add_job(
        scheduled_weekly_summary,
        'cron',
        day_of_week='fri',
        hour=20,
        minute=0,
        args=[client, pool],
        id='weekly_summary_job',
        name='Weekly Summary',
        replace_existing=True,
        misfire_grace_time=3600
    )

    # Публикация запланированных постов (каждые 5 минут)
    scheduler.add_job(
        publish_scheduled_post,
        'interval',
        minutes=5,
        args=[pool, client],
        id='publish_scheduled_posts',
        name='Publish Scheduled Posts',
        replace_existing=True,
        misfire_grace_time=300
    )

    print("Scheduler has been configured with jobs.")
    return scheduler
