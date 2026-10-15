import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_secret_key_123')
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI", "sqlite:///fallback.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Added pool_pre_ping and pool_recycle to prevent "Lost connection to MySQL server" errors
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'ssl': {}},
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "fallback_token_for_dev")
