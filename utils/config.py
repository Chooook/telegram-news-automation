import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / 'config.yml'

# Secrets from .env
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Load configuration from config.yml
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f) or {}  # Return empty dict if config is empty

# Telegram settings
TELEGRAM_CHANNEL = config.get('telegram_channel')
TARGET_CHANNEL = config.get('target_channel')

# Database settings
DB_CONFIG = config.get('postgres', {})
DB_NAME = DB_CONFIG.get('dbname')
DB_USER = DB_CONFIG.get('user')
DB_HOST = DB_CONFIG.get('host')
DB_PORT = DB_CONFIG.get('port')

# Parsing settings
INTERVALS = config.get('intervals', {})
PARSING_INTERVAL = config.get('parsing_interval')
SOURCES = config.get('sources', [])

# Admin user ids: объединяем из .env и config.yml
env_admins = [int(admin_id) for admin_id in os.getenv('ADMIN_USER_IDS', '').split(',') if admin_id]
config_admins = config.get('admin_user_ids', [])
ADMIN_USER_IDS = list(set(env_admins + config_admins))
