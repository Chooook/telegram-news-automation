from typing import List, Dict

def generate_summary(theme: str, articles: List[Dict]) -> str:
    """
    Generates a summary for a given theme based on a list of articles.
    
    This is a placeholder implementation. For a real-world scenario,
    this function should use a powerful language model (LLM) to generate
    a coherent and informative summary.
    """
    if not articles:
        return f"На этой неделе не было найдено статей по теме '{theme}'."

    summary = f"Еженедельный дайджест по теме: '{theme}'\n\n"
    summary += "Основные моменты недели:\n"
    
    for article in articles:
        summary += f"- {article['title']}\n"
        
    summary += "\nПодробности в следующих публикациях!"
    
    return summary
