import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_secret_key_123')
    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://3a5i58AzZzaidbB.root:MRslIm3cVtCZU77r@gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000/doseTrack"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Added pool_pre_ping and pool_recycle to prevent "Lost connection to MySQL server" errors
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'ssl': {}},
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    TELEGRAM_BOT_TOKEN = "8615887860:AAHixEeOgVoEZzijqgpgF7-6LvYB_GWxN14"
