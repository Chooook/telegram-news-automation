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
    
    The scheduler manages the following automated tasks:
    - Content parsing and embedding updates
    - Weekly theme setting and announcements
    - Daily content posting (morning and evening)
    - Weekly summary generation
    """
    scheduler = AsyncIOScheduler()

    # 1. Content Collection and Processing
    # Schedule parsing to run every 4 hours
    scheduler.add_job(
        scheduled_parsing, 
        'interval', 
        hours=4, 
        args=[client, pool],
        id='parsing_job',
        name='Content Parsing',
        replace_existing=True,
        misfire_grace_time=300  # 5 minutes grace period
    )

    # Schedule embedding updates to run every 4 hours, offset from parsing
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
    # Monday 9:00 - Set new weekly theme
    scheduler.add_job(
        scheduled_weekly_theme,
        'cron',
        day_of_week='mon',
        hour=9,
        minute=0,
        args=[client, pool],
        id='weekly_theme_job',
        name='Set Weekly Theme',
        replace_existing=True,
        timezone='Europe/Moscow'
    )
    
    # Tuesday-Friday 10:00 - Morning post (technical/in-depth)
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-fri',
        hour=10,
        minute=0,
        args=[client, pool, 'morning'],
        id='morning_post_job',
        name='Morning Post',
        replace_existing=True,
        timezone='Europe/Moscow'
    )
    
    # Tuesday-Friday 19:00 - Evening post (engaging/entertaining)
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-fri',
        hour=19,
        minute=0,
        args=[client, pool, 'evening'],
        id='evening_post_job',
        name='Evening Post',
        replace_existing=True,
        timezone='Europe/Moscow'
    )
    
    # Friday 20:00 - Post weekly summary
    scheduler.add_job(
        scheduled_weekly_summary,
        'cron',
        day_of_week='fri',
        hour=20,
        minute=0,
        args=[client, pool],
        id='weekly_summary_job',
        name='Weekly Summary',
        timezone='Europe/Moscow',
        replace_existing=True,
        misfire_grace_time=3600  # 1 hour grace period
    )
    
    # Schedule post publishing - runs every 5 minutes to check for posts to publish
    scheduler.add_job(
        publish_scheduled_post,
        'interval',
        minutes=5,
        args=[pool, client],
        id='publish_scheduled_posts',
        name='Publish Scheduled Posts',
        replace_existing=True,
        misfire_grace_time=300  # 5 minutes grace period
    )

    # Tuesday-Thursday - Daily posts at 12:00 and 19:00
    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-thu',
        hour=12,
        minute=0,
        args=[client, pool, 'morning'],
        id='morning_post_job',
        name='Morning Post',
        replace_existing=True
    )

    scheduler.add_job(
        scheduled_post_publication,
        'cron',
        day_of_week='tue-thu',
        hour=19,
        minute=0,
        args=[client, pool, 'evening'],
        id='evening_post_job',
        name='Evening Post',
        replace_existing=True
    )

    # Friday 9:00 - Weekly summary
    scheduler.add_job(
        scheduled_weekly_summary, 
        'cron', 
        day_of_week='fri', 
        hour=9,
        minute=0,
        args=[client, pool],
        id='weekly_summary_job',
        name='Weekly Summary',
        replace_existing=True
    )
    
    # Keep some posts on Friday for continuity
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
    
    # Weekend - No posts scheduled, but keep updating content
    # (parsing and embedding updates continue on weekends)

    print("Scheduler has been configured with jobs.")
    return scheduler
