from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .jobs import (
    scheduled_parsing, 
    scheduled_embedding_update, 
    scheduled_weekly_summary,
    scheduled_post_publication
)

def setup_scheduler(client, pool):
    """Initializes and configures the scheduler."""
    scheduler = AsyncIOScheduler()

    # Schedule parsing to run every 4 hours
    scheduler.add_job(
        scheduled_parsing, 
        'interval', 
        hours=4, 
        args=[client, pool],
        id='parsing_job'
    )

    # Schedule embedding updates to run every 4 hours, offset from parsing
    scheduler.add_job(
        scheduled_embedding_update, 
        'interval', 
        hours=4, 
        minutes=5, # Run 5 mins after parsing job
        args=[pool],
        id='embedding_job'
    )

    # Schedule weekly summary every Friday at 9 AM
    scheduler.add_job(
        scheduled_weekly_summary, 
        'cron', 
        day_of_week='fri', 
        hour=9, 
        args=[client, pool],
        id='summary_job'
    )

    # Schedule post publication twice a day on weekdays
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='mon-fri',
        hour='12,19',
        args=[client, pool],
        id='post_publication_job'
    )

    print("Scheduler has been configured with jobs.")
    return scheduler
