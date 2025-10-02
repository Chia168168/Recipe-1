from models import db, IngredientDB

def init_db(app):
    """初始化資料庫"""
    db.init_app(app)
    
    with app.app_context():
        try:
            # 創建所有表
            db.create_all()
            print("資料庫表創建成功")
            
            # 添加預設食材資料
            default_ingredients = [
                {"name": "水", "hydration": 100},
                {"name": "煉乳", "hydration": 30},
                {"name": "鮮奶油", "hydration": 50},
                {"name": "優格", "hydration": 90},
                {"name": "奶油乳酪", "hydration": 50},
                {"name": "牛奶", "hydration": 90},
                {"name": "雞蛋", "hydration": 75},
                {"name": "蜂蜜", "hydration": 17}
            ]
            
            for ing_data in default_ingredients:
                if not IngredientDB.query.filter_by(name=ing_data["name"]).first():
                    ingredient = IngredientDB(
                        name=ing_data["name"],
                        hydration=ing_data["hydration"]
                    )
                    db.session.add(ingredient)
            
            db.session.commit()
            print("預設食材添加成功")
            
        except Exception as e:
            print(f"資料庫初始化錯誤: {e}")
            raise
