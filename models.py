from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Recipe(db.Model):
    __tablename__ = 'recipes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    steps = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    top_heat = db.Column(db.Integer, default=200)
    bottom_heat = db.Column(db.Integer, default=200)
    baking_time = db.Column(db.Integer, default=30)
    convection = db.Column(db.Boolean, default=False)
    steam = db.Column(db.Boolean, default=False)
    
    # 關聯到食材
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade='all, delete-orphan')

class Ingredient(db.Model):
    __tablename__ = 'ingredients'
    
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    group = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    weight = db.Column(db.Float, default=0)
    percent = db.Column(db.Float)
    description = db.Column(db.String(200))

class IngredientDB(db.Model):
    __tablename__ = 'ingredient_database'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    hydration = db.Column(db.Float, default=0)
