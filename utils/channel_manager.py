import yaml
import os
from typing import List, Dict, Any, Optional

class ChannelManager:
    def __init__(self, config_path: str):
        """
        Инициализация менеджера каналов.
        
        Args:
            config_path: Путь к файлу конфигурации
        """
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Загружает конфигурацию из файла."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}
    
    def _save_config(self) -> bool:
        """Сохраняет конфигурацию в файл."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении конфигурации: {e}")
            return False
    
    def add_channel(self, name: str, username: str, tags: List[str]) -> bool:
        """
        Добавляет новый Telegram-канал в конфигурацию.
        
        Args:
            name: Название канала
            username: Имя пользователя канала (без @)
            tags: Список тегов
            
        Returns:
            bool: Успешно ли добавлен канал
        """
        if not self.config.get('sources'):
            self.config['sources'] = []
        
        # Проверяем, нет ли уже такого канала
        for source in self.config['sources']:
            if source.get('type') == 'telegram_web' and source.get('username') == username:
                print(f"Канал @{username} уже существует в конфигурации")
                return False
        
        # Добавляем новый канал
        new_channel = {
            'name': name,
            'type': 'telegram_web',
            'username': username.lstrip('@'),
            'tags': tags
        }
        
        self.config['sources'].append(new_channel)
        return self._save_config()
    
    def remove_channel(self, username: str) -> bool:
        """
        Удаляет канал из конфигурации.
        
        Args:
            username: Имя пользователя канала (с @ или без)
            
        Returns:
            bool: Успешно ли удален канал
        """
        username = username.lstrip('@')
        if not self.config.get('sources'):
            return False
            
        initial_length = len(self.config['sources'])
        self.config['sources'] = [
            source for source in self.config['sources']
            if not (source.get('type') == 'telegram_web' and source.get('username') == username)
        ]
        
        if len(self.config['sources']) < initial_length:
            return self._save_config()
        return False
    
    def list_channels(self) -> List[Dict[str, Any]]:
        """
        Возвращает список всех Telegram-каналов.
        
        Returns:
            List[Dict]: Список словарей с информацией о каналах
        """
        if not self.config.get('sources'):
            return []
            
        return [
            {
                'name': source.get('name', ''),
                'username': source.get('username', ''),
                'tags': ', '.join(source.get('tags', [])),
                'type': source.get('type', '')
            }
            for source in self.config['sources']
            if source.get('type') == 'telegram_web'
        ]
    
    def update_channel(self, username: str, **kwargs) -> bool:
        """
        Обновляет информацию о канале.
        
        Args:
            username: Имя пользователя канала (с @ или без)
            **kwargs: Поля для обновления (name, tags)
            
        Returns:
            bool: Успешно ли обновлен канал
        """
        username = username.lstrip('@')
        if not self.config.get('sources'):
            return False
            
        updated = False
        for source in self.config['sources']:
            if source.get('type') == 'telegram_web' and source.get('username') == username:
                if 'name' in kwargs:
                    source['name'] = kwargs['name']
                if 'tags' in kwargs:
                    source['tags'] = kwargs['tags']
                updated = True
                break
                
        if updated:
            return self._save_config()
        return False

# Пример использования
if __name__ == "__main__":
    # Инициализируем менеджер с путем к конфигу
    manager = ChannelManager('config.yml')
    
    # Добавляем канал
    manager.add_channel(
        name="Тестовый канал",
        username="test_channel",
        tags=["test", "example"]
    )
    
    # Список всех каналов
    channels = manager.list_channels()
    print("Список каналов:")
    for channel in channels:
        print(f"- {channel['name']} (@{channel['username']}): {channel['tags']}")
    
    # Удаляем канал
    # manager.remove_channel("test_channel")
