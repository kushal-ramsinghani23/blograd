from flask import Flask
from .routes.websites import website_bp
from .routes.keywords import keyword_bp
from .routes.drafts import draft_bp
from .routes.agent import agent_bp
from .extensions import db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blograd.db'

db.init_app(app)

app.register_blueprint(website_bp) # Register BP after init_app()
app.register_blueprint(keyword_bp)
app.register_blueprint(draft_bp)
app.register_blueprint(agent_bp)

with app.app_context():
    db.create_all()