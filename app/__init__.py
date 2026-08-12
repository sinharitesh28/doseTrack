from flask import Flask
from .config import Config
from .database import db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'ssl': {'ca': '/etc/ssl/certs/ca-certificates.crt'}}}
    db.init_app(app)

    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app
