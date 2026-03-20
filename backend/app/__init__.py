from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from .routes.urls import website_bp
from .extensions import db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blograd.db'

db.init_app(app)

app.register_blueprint(website_bp) # Register BP after init_app()

with app.app_context():
    db.create_all()