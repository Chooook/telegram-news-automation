import logging
import asyncpg
from pgvector.asyncpg import register_vector
from utils.config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

logger = logging.getLogger(__name__)

# Список разрешенных таблиц для запросов статуса
SAFE_TABLES = ['news', 'article_embeddings', 'published_links', 'settings',
               'admins', 'channels']


async def init_db_pool():
    """Initializes the database connection pool with pgvector support."""
    try:
        async def init_connection(conn):
            # Register vector type for each new connection
            await register_vector(conn)
            # Set a statement timeout to prevent long-running queries
            await conn.execute('SET statement_timeout = 60000')  # 60 seconds

        # Create the connection pool with our initialization
        pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            init=init_connection,
            min_size=1,
            max_size=10,
            command_timeout=60.0  # 60 seconds
        )

        # Verify the connection works with vector operations
        async with pool.acquire() as conn:
            await conn.execute('SELECT 1')

        logger.info(
            "Database pool initialized successfully with pgvector support.")
        return pool

    except Exception as e:
        logger.error(
            f"Ошибка при инициализации пула соединений с базой данных: {str(e)}")
        logger.error(
            "Проверьте настройки подключения к базе данных и убедитесь, что:")
        logger.error("1. База данных PostgreSQL запущена и доступна")
        logger.error("2. Указаны правильные учетные данные в файле .env")
        logger.error("3. Расширение pgvector установлено в базе данных")
        raise


async def ensure_database_schema(pool):
    """Ensures all database tables and extensions are properly set up."""
    try:
        async with pool.acquire() as conn:
            # Create extension if possible
            try:
                await conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
            except Exception as e:
                logger.warning(
                    f"Could not create vector extension (it might already exist): {e}")

            # Create tables if they don't exist
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT UNIQUE NOT NULL,
                    description TEXT,
                    source TEXT,
                    tags TEXT[],
                    published TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Add published column if it doesn't exist
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'news' AND column_name = 'published') THEN
                        ALTER TABLE news ADD COLUMN published TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
                        -- Update existing records with current timestamp if published is NULL
                        UPDATE news SET published = CURRENT_TIMESTAMP WHERE published IS NULL;
                    END IF;
                END $$;
                
                CREATE TABLE IF NOT EXISTS article_embeddings (
                    article_id TEXT PRIMARY KEY REFERENCES news(link) ON DELETE CASCADE,
                    embedding vector(384) NOT NULL
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
                username TEXT PRIMARY KEY,
                added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
                
                CREATE TABLE IF NOT EXISTS channel_states (
                    username TEXT PRIMARY KEY,
                    last_message_id INTEGER NOT NULL
                );
            """)

            # Исправляем формат существующих эмбеддингов
            await fix_existing_embeddings(pool)

            logger.info("Database schema verified and ready.")

    except Exception as e:
        logger.error(f"Error ensuring database schema: {str(e)}",
                     exc_info=True)
        raise


async def init_db(pool):
    """Initializes the database schema and fixes any embedding format issues."""
    try:
        await ensure_database_schema(pool)
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}",
                     exc_info=True)
        raise


async def save_article(pool, title, link, description, source, tags,
                       published=None):
    """
    Saves a new article to the database.

    Args:
        pool: Database connection pool
        title: Article title
        link: Article URL (unique)
        description: Article description/content
        source: Source of the article
        tags: List of tags
        published: Optional publication timestamp (defaults to current time if None)
    """
    try:
        async with pool.acquire() as conn:
            if published is None:
                # If published date is not provided, use current timestamp
                await conn.execute("""
                    INSERT INTO news (title, link, description, source, tags, published)
                    VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
                    ON CONFLICT (link) 
                    DO UPDATE SET 
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        source = EXCLUDED.source,
                        tags = EXCLUDED.tags,
                        published = COALESCE(news.published, EXCLUDED.published)
                """, title, link, description, source, tags)
            else:
                # If published date is provided, use it
                await conn.execute("""
                    INSERT INTO news (title, link, description, source, tags, published)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (link) 
                    DO UPDATE SET 
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        source = EXCLUDED.source,
                        tags = EXCLUDED.tags,
                        published = COALESCE(news.published, EXCLUDED.published)
                """, title, link, description, source, tags, published)
    except Exception as e:
        logger.error(f"Error saving article: {str(e)}", exc_info=True)
        raise


async def get_articles_without_embeddings(pool):
    """
    Fetches articles that do not have an embedding yet.

    Returns:
        List of articles with their details including published date
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT n.link, n.title, n.description, n.published 
            FROM news n
            LEFT JOIN article_embeddings ae ON n.link = ae.article_id
            WHERE ae.article_id IS NULL
            ORDER BY n.published DESC;
        """)


async def add_embedding(pool, article_id, embedding):
    """
    Добавляет или обновляет эмбеддинг для статьи в правильном формате [1.0, 2.0, 3.0].
    """
    try:
        # Проверяем, что embedding - это список чисел
        if not isinstance(embedding, (list, tuple)):
            raise ValueError(
                f"Эмбеддинг должен быть списком чисел, получен: {type(embedding)}")

        # Убедимся, что все элементы - числа
        embedding_list = [float(x) for x in embedding]
        if len(embedding_list) != 384:
            raise ValueError(
                f"Эмбеддинг должен содержать 384 числа, получено: {len(embedding_list)}")

        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO article_embeddings (article_id, embedding)
                VALUES ($1, $2::vector(384))
                ON CONFLICT (article_id) 
                DO UPDATE SET embedding = EXCLUDED.embedding
            """, article_id, embedding_list)
            logger.debug(f"Успешно сохранен эмбеддинг для статьи {article_id}")
    except Exception as e:
        logger.error(
            f"Ошибка при сохранении эмбеддинга для статьи {article_id}: {e}",
            exc_info=True)
        raise


async def fix_existing_embeddings(pool):
    """Исправляет формат существующих эмбеддингов в базе данных."""
    try:
        async with pool.acquire() as conn:
            # Проверяем, есть ли эмбеддинги в неправильном формате
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM article_embeddings 
                WHERE embedding::text LIKE '{%}';
            """)

            if count == 0:
                logger.info("Нет эмбеддингов в неправильном формате.")
                return 0

            logger.info(
                f"Найдено {count} эмбеддингов в неправильном формате, исправляем...")

            # Обновляем формат эмбеддингов
            await conn.execute("""
                UPDATE article_embeddings 
                SET embedding = REPLACE(REPLACE(embedding::text, '{', '['), '}', ']')::vector(384)
                WHERE embedding::text LIKE '{%}';
            """)

            logger.info(f"Успешно исправлено {count} эмбеддингов.")
            return count

    except Exception as e:
        logger.error(f"Ошибка при исправлении формата эмбеддингов: {e}",
                     exc_info=True)
        raise


async def find_similar_articles(pool, embedding, limit=5, start_date=None,
                                end_date=None):
    """
    Finds articles with embeddings similar to the given one, optionally filtered by date range.

    Args:
        pool: Database connection pool
        embedding: The embedding vector to compare against
        limit: Maximum number of results to return
        start_date: Optional start date for filtering articles (inclusive)
        end_date: Optional end date for filtering articles (inclusive)

    Returns:
        List of similar articles with their similarity scores
    """
    try:
        query = """
            SELECT ae.article_id, n.title, n.description, n.link,
                   n.source, n.tags, n.published,
                   1 - (ae.embedding <=> $1) as similarity
            FROM article_embeddings ae
            JOIN news n ON ae.article_id = n.link
            WHERE 1=1
        """

        params = [embedding]
        param_count = 1  # Start from 1 because $1 is already used for embedding

        # Add date filtering if dates are provided
        if start_date:
            param_count += 1
            query += f" AND n.published >= ${param_count}::timestamptz"
            params.append(start_date)

        if end_date:
            param_count += 1
            # Add one day to end_date to include the entire end day
            query += f" AND n.published < (${param_count}::date + interval '1 day')::timestamptz"
            params.append(end_date)

        # Add ordering and limit
        query += " ORDER BY ae.embedding <=> $1"
        param_count += 1
        query += f" LIMIT ${param_count}"
        params.append(limit)

        async with pool.acquire() as conn:
            return await conn.fetch(query, *params)

    except Exception as e:
        logger.error(f"Error finding similar articles: {str(e)}",
                     exc_info=True)
        return []


async def get_db_status(pool):
    """Gets the count of records in key tables."""
    async with pool.acquire() as connection:
        status = {}
        for table in SAFE_TABLES:
            try:
                # Безопасный запрос с использованием белого списка таблиц
                count = await connection.fetchval(
                    f'SELECT COUNT(*) FROM {table};')
                status[table] = count
            except Exception as e:
                status[table] = f"Error: {e}"
        return status


async def get_admins(pool):
    async with pool.acquire() as conn:
        admins = await conn.fetch("SELECT user_id FROM admins")
        return [row['user_id'] for row in admins]


async def add_admin(pool, user_id):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO admins (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_id)
        logger.info(f"Admin added: {user_id}")


async def remove_admin(pool, user_id):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM admins WHERE user_id = $1", user_id)
        logger.info(f"Admin removed: {user_id}")


async def get_setting(pool, key):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT value FROM settings WHERE key = $1",
                                   key)


async def set_setting(pool, key, value):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2
        """, key, value)
        logger.info(f"Setting updated: {key} = {value}")


async def get_published_links(pool):
    async with pool.acquire() as conn:
        links = await conn.fetch("SELECT link FROM published_links")
        return {row['link'] for row in links}


async def add_published_link(pool, link):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO published_links (link) VALUES ($1) ON CONFLICT DO NOTHING",
            link)


async def add_channel(pool, username):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO channels (username) VALUES ($1) ON CONFLICT (username) DO NOTHING",
            username)
        logger.info(f"Channel added: {username}")


async def get_channels(pool):
    """Gets the list of all channels."""
    async with pool.acquire() as conn:
        return [row['username'] for row in
                await conn.fetch("SELECT username FROM channels")]


async def remove_channel(pool, username):
    """Removes a channel from the database."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM channels WHERE username = $1",
                           username)
        return [row['username'] for row in
                await conn.fetch("SELECT username FROM channels")]


async def get_articles_by_date_range(pool, start_date, end_date):
    """
    Retrieves articles published within a specified date range.

    Args:
        pool: Database connection pool
        start_date: Start date (inclusive) in 'YYYY-MM-DD' format
        end_date: End date (inclusive) in 'YYYY-MM-DD' format

    Returns:
        List of articles with their details
    """
    query = """
        SELECT id, title, link, description, source, tags, published as published_at 
        FROM news 
        WHERE published >= $1::timestamptz 
        AND published < ($2::date + interval '1 day')::timestamptz
        ORDER BY published DESC
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, start_date, end_date)
            return [dict(row) for row in rows] if rows else []
    except Exception as e:
        logger.error(f"Error fetching articles by date range: {e}",
                     exc_info=True)
        return []


async def get_last_message_id(pool, channel_username):
    """Gets the last processed message ID for a channel."""
    async with pool.acquire() as conn:
        last_id = await conn.fetchval(
            'SELECT last_message_id FROM channel_states WHERE username = $1',
            channel_username)
        return last_id or 0


async def update_last_message_id(pool, channel_username, message_id):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO channel_states (username, last_message_id)
            VALUES ($1, $2)
            ON CONFLICT (username) DO UPDATE SET last_message_id = $2
        """, channel_username, message_id)


async def ensure_vector_extension_exists():
    """Ensures the vector extension is created and properly set up."""
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
        await register_vector(conn)

        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'article_embeddings'
            )
            """
        )

        if table_exists:
            column_type = await conn.fetchval(
                """
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'article_embeddings' 
                AND column_name = 'embedding'
                """
            )

            if column_type != 'USER-DEFINED':
                await conn.execute('''
                    ALTER TABLE article_embeddings 
                    ALTER COLUMN embedding TYPE vector(384) USING REPLACE(REPLACE(embedding::text, '{', '['), '}', ']')::vector(384);
                ''')
                logger.info("Converted embedding column to vector(384) type.")

        logger.info(
            "Vector extension and database schema verified successfully.")

    except Exception as e:
        if "permission denied" in str(e).lower() or "must be superuser" in str(
                e).lower():
            logger.warning(
                "Недостаточно прав для настройки расширения vector. Требуются права суперпользователя.")
            logger.warning(
                "Пожалуйста, выполните вручную в psql: CREATE EXTENSION IF NOT EXISTS vector;")
        else:
            logger.error(f"Ошибка при настройке расширения vector: {e}",
                         exc_info=True)
            raise
    finally:
        if conn:
            await conn.close()
