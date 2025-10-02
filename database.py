from flask_sqlalchemy import SQLAlchemy
from models import db, Recipe, Ingredient, IngredientDB

def init_db(app):
    """初始化資料庫"""
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        
        # 添加預設食材資料
        default_ingredients = [
            {"name": "水", "hydration": 1.0},
            {"name": "煉乳", "hydration": 0.3},
            {"name": "鮮奶油", "hydration": 0.5},
            {"name": "優格", "hydration": 0.9},
            {"name": "奶油乳酪", "hydration": 0.5},
            {"name": "牛奶", "hydration": 0.9},
            {"name": "雞蛋", "hydration": 0.75},
            {"name": "蜂蜜", "hydration": 0.17}
        ]
        
        for ing_data in default_ingredients:
            if not IngredientDB.query.filter_by(name=ing_data["name"]).first():
                ingredient = IngredientDB(
                    name=ing_data["name"],
                    hydration=ing_data["hydration"]
                )
                db.session.add(ingredient)
        
        db.session.commit()
