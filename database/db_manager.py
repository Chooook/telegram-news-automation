import logging
import asyncpg
from pgvector.asyncpg import register_vector
from utils.config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

logger = logging.getLogger(__name__)




async def init_db_pool():
    """Initializes the database connection pool."""
    try:
        async def init_connection(conn):
            await register_vector(conn)

        pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            init=init_connection
        )
        logger.info("Database pool initialized successfully with pgvector.")
        return pool
    except Exception as e:
        logger.error(f"Error initializing database pool: {str(e)}")
        raise

async def init_db(pool):
    """Creates all necessary tables if they don't exist."""
    try:
        async with pool.acquire() as conn:

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT UNIQUE NOT NULL,
                    description TEXT,
                    source TEXT,
                    tags TEXT[]
                );
                CREATE TABLE IF NOT EXISTS article_embeddings (
                    article_link TEXT PRIMARY KEY REFERENCES news(link) ON DELETE CASCADE,
                    embedding VECTOR(384) NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS published_links (
                    link TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS channels (
                    username TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS channel_states (
                    username TEXT PRIMARY KEY,
                    last_message_id INTEGER NOT NULL
                );
            """)
            logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database tables: {str(e)}")
        raise

async def save_article(pool, title, link, description, source, tags):
    """Saves a new article to the database."""
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO news (title, link, description, source, tags)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (link) DO NOTHING
            """, title, link, description, source, tags)
    except Exception as e:
        logger.error(f"Error saving article: {str(e)}")
        raise

async def get_articles_without_embeddings(pool):
    """Fetches articles that do not have an embedding yet."""
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT n.link, n.title, n.description FROM news n
            LEFT JOIN article_embeddings ae ON n.link = ae.article_link
            WHERE ae.article_link IS NULL;
        """)

async def add_embedding(pool, article_link, embedding):
    """Adds a new embedding for an article."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO article_embeddings (article_link, embedding)
            VALUES ($1, $2)
            ON CONFLICT (article_link) DO NOTHING
        """, article_link, embedding)

async def find_similar_articles(pool, embedding, limit=5):
    """Finds articles with embeddings similar to the given one."""
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("""
                SELECT n.id, n.title, n.link, n.description, n.source, n.tags, 
                       1 - (ae.embedding <=> $1) as similarity
                FROM news n
                JOIN article_embeddings ae ON n.link = ae.article_link
                ORDER BY ae.embedding <=> $1
                LIMIT $2
            """, embedding, limit)

            return await conn.fetch(sql_query, *params)
    except Exception as e:
        logger.error(f"Error finding similar articles: {str(e)}")
        return []

async def get_db_status(pool):
    """Gets the count of records in key tables."""
    async with pool.acquire() as connection:
        status = {}
        tables = ['news', 'article_embeddings', 'published_links', 'settings', 'admins', 'channels']
        for table in tables:
            try:
                count = await connection.fetchval(f'SELECT COUNT(*) FROM {table};')
                status[table] = count
            except Exception as e:
                status[table] = f"Error: {e}"
        return status

# --- Admin and Settings Functions ---

async def get_admins(pool):
    async with pool.acquire() as conn:
        admins = await conn.fetch("SELECT user_id FROM admins")
        return [row['user_id'] for row in admins]

async def add_admin(pool, user_id):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO admins (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
        logger.info(f"Admin added: {user_id}")

async def remove_admin(pool, user_id):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM admins WHERE user_id = $1", user_id)
        logger.info(f"Admin removed: {user_id}")

async def get_setting(pool, key):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)

async def set_setting(pool, key, value):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2
        """, key, value)
        logger.info(f"Setting updated: {key} = {value}")

# --- Published Links and Channels Functions ---

async def get_published_links(pool):
    async with pool.acquire() as conn:
        links = await conn.fetch("SELECT link FROM published_links")
        return {row['link'] for row in links}

async def add_published_link(pool, link):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO published_links (link) VALUES ($1) ON CONFLICT DO NOTHING", link)

async def add_channel(pool, username):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO channels (username) VALUES ($1) ON CONFLICT (username) DO NOTHING", username)
        logger.info(f"Channel added: {username}")

async def get_channels(pool):
    async with pool.acquire() as conn:
        channels = await conn.fetch("SELECT username FROM channels")
        return [row['username'] for row in channels]

async def get_last_message_id(pool, channel_username):
    async with pool.acquire() as conn:
        last_id = await conn.fetchval("SELECT last_message_id FROM channel_states WHERE username = $1", channel_username)
        return last_id or 0

async def update_last_message_id(pool, channel_username, message_id):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO channel_states (username, last_message_id)
            VALUES ($1, $2)
            ON CONFLICT (username) DO UPDATE SET last_message_id = $2
        """, channel_username, message_id)

async def ensure_vector_extension_exists():
    """Ensures the vector extension is created before the pool is initialized."""
    conn = None
    try:
        conn = await asyncpg.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME
        )
        await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')
        logger.info("Vector extension checked/created successfully.")
    except Exception as e:
        if "permission denied" in str(e).lower() or "must be superuser" in str(e).lower():
            logger.warning("Нет прав для создания расширения vector. Проверьте, что оно уже установлено.")
        else:
            logger.error(f"Error ensuring vector extension exists: {e}")
            raise
    finally:
        if conn:
            await conn.close()
