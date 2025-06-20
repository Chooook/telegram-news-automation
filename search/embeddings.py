import os
import httpx
import asyncio
import logging
from typing import Optional, List, Dict, Any
from database.db_manager import get_articles_without_embeddings, add_embedding

# Настройка логирования
logger = logging.getLogger(__name__)

# Get API Key from environment variables
API_KEY = os.getenv("HF_API_TOKEN")
API_URL = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Таймауты в секундах
REQUEST_TIMEOUT = 30.0
MODEL_LOAD_TIMEOUT = 60.0
MAX_RETRIES = 3

async def generate_embedding(text: str, client: httpx.AsyncClient) -> Optional[List[float]]:
    """
    Генерирует векторное представление текста с использованием Hugging Face API.
    
    Args:
        text: Текст для векторизации
        client: HTTP-клиент для запросов
        
    Returns:
        Список чисел с плавающей точкой (эмбеддинг) или None в случае ошибки
    """
    if not text or not isinstance(text, str):
        logger.warning("Пустой или неверный формат текста для генерации эмбеддинга")
        return None

    payload = {
        "inputs": text,
        "options": {"wait_for_model": True}
    }
    
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Попытка {attempt + 1} генерации эмбеддинга для текста: {text[:100]}...")
            
            # Отправляем запрос с таймаутом
            response = await client.post(
                API_URL,
                headers=HEADERS,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
            
            # Если модель загружается, ждем и повторяем
            if response.status_code == 503:  # Model is loading
                wait_time = min(20 * (attempt + 1), 60)  # Увеличиваем время ожидания
                logger.warning(f"Модель загружается, ждем {wait_time} секунд...")
                await asyncio.sleep(wait_time)
                continue
                
            # Проверяем статус ответа
            response.raise_for_status()
            
            # Обрабатываем успешный ответ
            result = response.json()
            
            # Проверяем формат ответа
            if isinstance(result, list):
                if result and isinstance(result[0], float):
                    return result
                if result and isinstance(result[0], list):
                    return result[0]
            
            logger.warning(f"Неожиданный формат ответа API: {result}")
            return None
            
        except httpx.HTTPStatusError as e:
            last_error = f"Ошибка API (статус {e.response.status_code}): {e.response.text}"
            logger.error(last_error)
            if e.response.status_code == 429:  # Too Many Requests
                retry_after = int(e.response.headers.get('Retry-After', 30))
                await asyncio.sleep(retry_after)
            else:
                break
                
        except (httpx.RequestError, asyncio.TimeoutError) as e:
            last_error = f"Ошибка сети: {str(e)}"
            logger.error(last_error)
            await asyncio.sleep(5 * (attempt + 1))  # Экспоненциальная задержка
            
        except Exception as e:
            last_error = f"Неожиданная ошибка: {str(e)}"
            logger.exception("Ошибка при генерации эмбеддинга")
            break
    
    logger.error(f"Не удалось сгенерировать эмбеддинг после {MAX_RETRIES} попыток. Последняя ошибка: {last_error}")
    return None

async def update_embeddings(pool) -> Dict[str, int]:
    """
    Находит статьи без эмбеддингов, генерирует их и сохраняет в БД.
    
    Returns:
        Словарь со статистикой: {
            'total': общее количество статей,
            'processed': успешно обработано,
            'failed': не удалось обработать
        }
    """
    stats = {'total': 0, 'processed': 0, 'failed': 0}
    
    # Проверяем наличие API ключа
    if not API_KEY:
        error_msg = (
            "\nОШИБКА: Не найден API ключ Hugging Face.\n"
            "Пожалуйста, получите ключ на https://huggingface.co/settings/tokens\n"
            "и добавьте его в файл .env в формате:\n"
            'HF_API_TOKEN="hf_..."\n'
        )
        logger.error(error_msg)
        return stats

    logger.info("Начинаем обновление эмбеддингов...")
    
    try:
        # Получаем статьи без эмбеддингов
        articles_to_process = await get_articles_without_embeddings(pool)
        stats['total'] = len(articles_to_process)
        
        if not articles_to_process:
            logger.info("Нет статей для генерации эмбеддингов.")
            return stats

        logger.info(f"Найдено {stats['total']} статей без эмбеддингов")
        
        # Используем один HTTP-клиент для всех запросов
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            for i, article in enumerate(articles_to_process, 1):
                try:
                    logger.debug(f"Обработка статьи {i}/{stats['total']}: {article['link']}")
                    
                    # Формируем текст для эмбеддинга
                    text_to_embed = f"{article['title']} {article['description'] or ''}".strip()
                    if not text_to_embed:
                        logger.warning(f"Пустой текст для статьи {article['link']}")
                        stats['failed'] += 1
                        continue
                    
                    # Генерируем эмбеддинг
                    embedding = await generate_embedding(text_to_embed, client)
                    
                    if embedding is None:
                        logger.error(f"Не удалось сгенерировать эмбеддинг для статьи: {article['link']}")
                        stats['failed'] += 1
                        continue
                    
                    # Сохраняем эмбеддинг в БД
                    await add_embedding(pool, article['link'], embedding)
                    stats['processed'] += 1
                    
                    # Логируем прогресс
                    if i % 10 == 0 or i == stats['total']:
                        logger.info(f"Обработано {i}/{stats['total']} статей")
                    
                    # Небольшая задержка, чтобы не перегружать API
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке статьи {article.get('link', 'unknown')}: {str(e)}", exc_info=True)
                    stats['failed'] += 1
                    continue
        
        # Итоговая статистика
        logger.info(
            f"Завершено. Обработано: {stats['processed']}/"
            f"{stats['total']}, Ошибок: {stats['failed']}"
        )
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении эмбеддингов: {str(e)}", exc_info=True)
    
    return stats
