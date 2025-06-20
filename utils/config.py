import os
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Secrets from .env
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Load configuration from config.yml
with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)

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
