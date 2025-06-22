from sentence_transformers import SentenceTransformer
import numpy as np
import logging
from typing import Optional, List, Dict, Any
from database.db_manager import get_articles_without_embeddings, add_embedding

logger = logging.getLogger(__name__)
model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

async def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Генерирует векторное представление текста с использованием локальной модели.
    
    Args:
        text: Текст для векторизации
        
    Returns:
        Список чисел с плавающей точкой (эмбеддинг) или None в случае ошибки
    """
    if not text or not isinstance(text, str):
        logger.warning("Пустой или неверный формат текста для генерации эмбеддинга")
        return None
    try:
        embedding = model.encode(text, convert_to_numpy=True).tolist()
        logger.debug(f"Успешно сгенерирован эмбеддинг для текста: {text[:100]}...")
        return embedding
    except Exception as e:
        logger.error(f"Ошибка генерации эмбеддинга: {e}")
        return None

async def update_embeddings(pool, batch_size: int = 32) -> Dict[str, int]:
    """
    Находит статьи без эмбеддингов, генерирует их и сохраняет в БД.
    
    Args:
        pool: Пул подключений к БД
        batch_size: Размер батча для обработки (по умолчанию 32)
        
    Returns:
        Словарь со статистикой: {
            'processed': количество успешно обработанных статей,
            'errors': количество ошибок
        }
    """
    processed = 0
    errors = 0
    
    try:
        # Получаем все статьи без эмбеддингов
        articles = await get_articles_without_embeddings(pool)
        if not articles:
            logger.info("Нет статей для обновления эмбеддингов.")
            return {"processed": 0, "errors": 0}
            
        logger.info(f"Найдено {len(articles)} статей без эмбеддингов. Начинаем обработку...")
        
        # Обрабатываем статьи батчами
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            batch_texts = []
            valid_articles = []
            
            # Подготавливаем текст для эмбеддинга
            for article in batch:
                text_parts = []
                if article['title']:
                    text_parts.append(article['title'])
                if article['description']:
                    text_parts.append(article['description'])
                
                if not text_parts:
                    logger.warning(f"Пустые title и description у статьи {article['link']}")
                    errors += 1
                    continue
                
                # Используем published date для логирования, если доступно
                pub_date = article.get('published', 'без даты')
                logger.info(f"Обработка статьи: {article['title'][:50]}... (опубликовано: {pub_date})")
                
                text = ' '.join(text_parts)
                batch_texts.append(text)
                valid_articles.append(article)
            
            if not batch_texts:
                continue
                
            try:
                # Генерируем эмбеддинги для батча
                embeddings = model.encode(
                    batch_texts,
                    batch_size=len(batch_texts),
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
                
                # Сохраняем эмбеддинги
                for j, embedding in enumerate(embeddings):
                    if j >= len(valid_articles):
                        break
                        
                    article = valid_articles[j]
                    try:
                        # Преобразуем numpy массив в список
                        embedding_list = embedding.tolist()
                        
                        # Сохраняем эмбеддинг
                        await add_embedding(
                            pool=pool,
                            article_id=article['link'],
                            embedding=embedding_list
                        )
                        processed += 1
                        
                        if processed % 10 == 0:
                            logger.info(f"Обработано {processed} эмбеддингов...")
                            
                    except Exception as e:
                        logger.error(f"Ошибка при сохранении эмбеддинга для статьи {article.get('link', 'unknown')}: {e}")
                        errors += 1
                        
            except Exception as e:
                logger.error(f"Ошибка при генерации эмбеддингов для батча: {e}")
                errors += len(batch_texts)
                continue
                
        logger.info(f"Обновление эмбеддингов завершено. Обработано: {processed}, ошибок: {errors}")
        return {"processed": processed, "errors": errors}
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении эмбеддингов: {e}", exc_info=True)
        return {"processed": processed, "errors": errors + (len(articles) - processed) if 'articles' in locals() else 1}