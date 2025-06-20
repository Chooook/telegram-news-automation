import asyncio
from telethon import TelegramClient
from utils.config import API_ID, API_HASH, BOT_TOKEN
from database.db_manager import ensure_vector_extension_exists, init_db_pool, init_db
from bot.handlers import register_handlers
from scheduler.scheduler import setup_scheduler
from utils.logging_config import setup_logging

async def main():
    # 0. Setup logging
    setup_logging()

    # 1. Ensure pgvector extension exists and initialize DB
    print("Ensuring vector extension exists...")
    await ensure_vector_extension_exists()
    print("Initializing database pool...")
    pool = await init_db_pool()
    await init_db(pool)
    print("Database initialized.")

    # 2. Initialize Telegram client
    print("Initializing Telegram client...")
    client = TelegramClient('bot_session', API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)

    # 3. Setup bot handlers and scheduler
    print("Setting up bot handlers and scheduler...")
    await register_handlers(client, pool)
    scheduler = setup_scheduler(client, pool)

    # 4. Start the client and scheduler
    async with client:
        scheduler.start()
        print("Bot is running with scheduled jobs...")
        await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
