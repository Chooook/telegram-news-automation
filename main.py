import asyncio
from telethon import TelegramClient
from utils.config import API_ID, API_HASH, BOT_TOKEN
from database.db_manager import (
    ensure_vector_extension_exists, init_db_pool, init_db)
from bot.handlers import register_handlers
from scheduler.scheduler import setup_scheduler
from utils.logging_config import setup_logging


async def main():
    setup_logging()
    print("Starting bot initialization...")

    # Validate critical config
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        raise ValueError("Missing Telegram API configuration")

    try:
        print("Ensuring vector extension exists...")
        await ensure_vector_extension_exists()

        print("Initializing database pool...")
        pool = await init_db_pool()
        await init_db(pool)
        print("Database initialized successfully")
    except Exception as e:
        print("Database initialization failed")
        raise

    client = None
    try:
        print("Initializing Telegram client...")
        client = TelegramClient('bot_session', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)

        print("Setting up handlers and scheduler...")
        await register_handlers(client, pool)
        scheduler = setup_scheduler(client, pool)

        try:
            async with client:
                scheduler.start()
                print("Bot started with scheduled jobs")
                await client.run_until_disconnected()
        finally:
            print("Stopping scheduler...")
            scheduler.shutdown()
    except Exception as e:
        print("Fatal error in main loop")
    finally:
        print("Closing database pool...")
        await pool.close()
        if client and client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped by user")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        print("Event loop closed")
