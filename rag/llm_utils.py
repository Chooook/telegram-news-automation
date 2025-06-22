import logging
from typing import List, Dict, Optional
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import torch

logger = logging.getLogger(__name__)

# Initialize model and tokenizer as None (will be loaded on first use)
model = None
tokenizer = None
generator = None

def load_model():
    """Load the local language model and tokenizer."""
    global model, tokenizer, generator
    
    if model is None or tokenizer is None:
        try:
            model_name = "IlyaGusev/rugpt3_small_generic"  # Small Russian model that works well on CPU
            logger.info(f"Loading local model: {model_name}")
            
            # Load tokenizer and model
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                device_map="auto",
                torch_dtype=torch.float32,  # Always use float32 for CPU
                low_cpu_mem_usage=True
            )
            
            # Create text generation pipeline
            generator = pipeline(
                'text-generation',
                model=model,
                tokenizer=tokenizer,
                device=-1,  # Force CPU usage (-1 means CPU)
                framework='pt',
                model_kwargs={"torch_dtype": torch.float32}
            )
            logger.info("Model and tokenizer loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading model: {e}", exc_info=True)
            raise

async def generate_with_llm(prompt: str, max_tokens: int = 50) -> Optional[str]:
    """
    Generate text using a local language model.
    
    Args:
        prompt: The prompt for the model
        max_tokens: Maximum number of tokens to generate
        
    Returns:
        Generated text or None if error
    """
    try:
        if generator is None:
            load_model()
            
        # Generate text with more conservative settings for CPU
        output = generator(
            prompt,
            max_new_tokens=max_tokens,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            repetition_penalty=1.1,
            num_return_sequences=1,
            pad_token_id=tokenizer.eos_token_id
        )
        
        # Extract and clean the generated text
        generated_text = output[0]['generated_text'].replace(prompt, '').strip()
        
        # Remove any trailing incomplete sentences
        last_punct = max(
            generated_text.rfind('.'),
            generated_text.rfind('!'),
            generated_text.rfind('?'),
            generated_text.rfind(',')
        )
        
        if last_punct > 0:
            generated_text = generated_text[:last_punct + 1]
        
        # Clean up any remaining special tokens or artifacts
        generated_text = generated_text.split('\n')[0]  # Take first line if multiple
        generated_text = ' '.join(generated_text.split())  # Normalize whitespace
        
        return generated_text if generated_text else None
        
    except Exception as e:
        logger.error(f"Error generating text with local model: {e}", exc_info=True)
        return None

async def generate_theme_description(theme: str) -> str:
    """Generate a short description of the weekly theme."""
    prompt = (
        f"Напиши краткое описание темы '{theme}' простым языком, 2-3 предложения. "
        "Опиши, почему это важно и какие аспекты будут освещены. "
        "Не используй кавычки в ответе."
    )
    
    result = await generate_with_llm(prompt)
    return result or f"Тема недели: {theme}"

async def generate_article_summary(article: Dict[str, str]) -> str:
    """Generate a concise summary of an article."""
    prompt = (
        f"Создай краткое описание статьи в 2-3 предложения. "
        f"Заголовок: {article.get('title', '')}\n"
        f"Текст: {article.get('description', '')[:1000]}\n\n"
        "Опиши простым языком, о чем статья, без технических деталей. "
        "Не используй кавычки в ответе."
    )
    
    result = await generate_with_llm(prompt)
    return result or article.get('title', 'Без названия')

def should_exclude_article(article: Dict[str, str]) -> bool:
    """Check if article should be excluded based on title."""
    exclude_keywords = [
        'созвон', 'запись', 'записаться', 'зарегистрироваться',
        'регистрация', 'вебинар', 'митап', 'конференция',
        'приглашение', 'анонс', 'анонсируем', 'анонсируем'
    ]
    
    title = article.get('title', '').lower()
    return any(keyword in title for keyword in exclude_keywords)
