ADMIN_COMMANDS_MAP = {
    "1": "Статус",
    "2": "Задать тему недели",
    "3": "Добавить статью",
    "4": "Поиск",
    "5": "Управление каналами",
    "6": "Управление админами",
    "7": "Запустить парсинг",
    "8": "Генерация эмбеддингов",
    "9": "Создать саммари",
    "10": "Состояние базы",
    "11": "Просмотр логов",
    "12": "Тренировка недельного сценария"
}

CHANNEL_COMMANDS_MAP = {
    "1": "Список каналов",
    "2": "Добавить канал",
    "3": "Удалить канал",
    "0": "Назад в главное меню"
}

ADMIN_MANAGEMENT_MAP = {
    "1": "Список админов",
    "2": "Добавить админа",
    "3": "Удалить админа",
    "0": "Назад в главное меню"
}

def get_admin_menu_text():
    """Генерирует текстовое представление админ-меню."""
    menu_items = [f"{num}. {name}" for num, name in ADMIN_COMMANDS_MAP.items()]
    menu_text = "Добро пожаловать в админ-панель!\n\n"
    menu_text += "Выберите действие, отправив его номер:\n"
    menu_text += "\n".join(menu_items)
    return menu_text

def get_channels_menu_text():
    """Генерирует текстовое представление меню управления каналами."""
    menu_items = [f"{num}. {name}" for num, name in CHANNEL_COMMANDS_MAP.items()]
    menu_text = "Управление каналами для парсинга\n\n"
    menu_text += "Выберите действие, отправив его номер:\n"
    menu_text += "\n".join(menu_items)
    return menu_text


def get_admin_management_menu_text():
    """Генерирует текстовое представление меню управления админами."""
    menu_items = [f"{num}. {name}" for num, name in ADMIN_MANAGEMENT_MAP.items()]
    menu_text = "Управление администраторами\n\n"
    menu_text += "Выберите действие, отправив его номер:\n"
    menu_text += "\n".join(menu_items)
    return menu_text
