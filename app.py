# app.py (PostgreSQL 版本)
import os
import re
from datetime import datetime
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import TypeDecorator, Text
import json

# --- 1. 設置資料庫連線 ---
# Render 會自動提供 DATABASE_URL 環境變數
# 注意：psycopg2 預設使用 postgres://，Render 使用 postgresql://，需要替換
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///recipes.db').replace("postgres://", "postgresql://")

# 設置 Flask 和 SQLAlchemy
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL

# 創建引擎和會話
engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# --- 2. 自訂 JSON 欄位類型 (用於儲存食譜中的食材列表) ---
class JSONEncodedDict(TypeDecorator):
    """將 Python 字典或列表儲存為 PostgreSQL 的 TEXT/JSONB 欄位。"""
    impl = Text
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value

# --- 3. 定義資料模型 (Models) ---

class Recipe(Base):
    __tablename__ = 'recipes'
    
    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True, nullable=False)
    ingredients = Column(JSONEncodedDict) # 儲存食材列表 (JSON/JSONB)
    steps = Column(Text)
    top_heat = Column(Float)
    bottom_heat = Column(Float)
    baking_time = Column(Float)
    convection = Column(Boolean)
    steam = Column(Boolean)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'title': self.title,
            'ingredients': self.ingredients,
            'steps': self.steps,
            'baking': {
                'topHeat': self.top_heat,
                'bottomHeat': self.bottom_heat,
                'time': self.baking_time,
                'convection': self.convection,
                'steam': self.steam,
            },
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }

class IngredientDB(Base):
    __tablename__ = 'ingredients_db'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    hydration = Column(Float, nullable=False)

    def to_dict(self):
        return {
            'name': self.name,
            'hydration': self.hydration
        }

# 在應用程式啟動時創建資料表
def init_db():
    Base.metadata.create_all(engine)

# --- 4. 輔助函數 (與原 Apps Script 邏輯保持一致) ---

# 注意：因為這些函數不直接依賴資料庫讀寫，所以可以直接沿用或微調。
def normalize_percent_value(p):
    # (保持不變的 normalize_percent_value 函數邏輯)
    if p is None or p == "":
        return ""
    # ... (此處省略詳細實現以保持簡潔，請確保使用上一個回答中的 Python 實現)
    if isinstance(p, str):
        s = p.strip()
        if s.endswith('%'):
            try:
                n = float(s.replace('%','').strip())
                return n / 100.0 if not (n is None or n == "") else ""
            except ValueError:
                return ""
        try:
            n = float(s)
            return n / 100.0 if n > 1 else n
        except ValueError:
            return ""
    
    if isinstance(p, (int, float)):
        return p / 100.0 if p > 1 else p
    
    return ""
    
def calculate_hydration(ingredients, ingredients_db):
    # (保持不變的 calculate_hydration 函數邏輯)
    # ... (此處省略詳細實現以保持簡潔，請確保使用上一個回答中的 Python 實現)
    flour_total = 0
    water_total = 0
    
    db_dict = {item['name']: item['hydration'] for item in ingredients_db}
    
    def is_flour(name):
        return any(keyword in name for keyword in ["麵粉", "高筋", "低筋", "全麥", "粉"])
    def is_water(name):
        return any(keyword in name for keyword in ["水", "牛奶", "液", "汁"])
    def is_egg(name):
        return "蛋" in name
    
    def is_percentage_group(group_name):
        group_name = group_name.strip()
        return not (group_name == "內餡" or group_name == "裝飾")
    
    for ing in ingredients:
        weight = float(ing.get('weight', 0) or 0)
        name = ing.get('name', '')
        group = ing.get('group', '')
        
        if weight <= 0 or not is_percentage_group(group):
            continue

        hydration_rate = db_dict.get(name)
        
        if hydration_rate is not None and hydration_rate != "":
            hydration_rate = float(hydration_rate)
            if hydration_rate > 100: hydration_rate = 100
            
            if hydration_rate > 0 and hydration_rate < 100:
                water_equivalent = weight * (hydration_rate / 100.0)
                flour_equivalent = weight * ((100.0 - hydration_rate) / 100.0)
                flour_total += flour_equivalent
                water_total += water_equivalent
                
            elif hydration_rate == 0:
                flour_total += weight
            elif hydration_rate == 100:
                water_total += weight
                
        elif is_flour(name):
            flour_total += weight
        elif is_water(name):
            water_total += weight
        elif is_egg(name):
            water_total += weight * 0.75
            
    if flour_total > 0:
        hydration = (water_total / flour_total) * 100
        return f"{hydration:.2f}%"
    else:
        return "0%"

# --- 5. API 路由 (替換數據讀寫邏輯) ---

@app.route('/', methods=['GET'])
def serve_index():
    """根路由：提供 index.html 內容。"""
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    """取得所有食譜列表 (DB 讀取)。"""
    session = Session()
    try:
        # 讀取所有食譜
        recipes_list = [r.to_dict() for r in session.query(Recipe).all()]
        
        # 讀取食材資料庫
        ingredients_db = [i.to_dict() for i in session.query(IngredientDB).all()]
        
        # 計算含水率
        for recipe in recipes_list:
            recipe['hydration'] = calculate_hydration(recipe.get('ingredients', []), ingredients_db)
            
        return jsonify(recipes_list)
    finally:
        session.close()

@app.route('/api/recipe', methods=['POST'])
def save_recipe():
    """新增食譜 (DB 寫入)。"""
    recipe_data = request.json
    title = recipe_data.get('title')
    
    if not title:
        return jsonify({"status": "error", "message": "食譜名稱不能為空"}), 400

    session = Session()
    try:
        # 檢查食譜是否已存在
        if session.query(Recipe).filter_by(title=title).first():
            return jsonify({"status": "error", "message": f"食譜 '{title}' 已存在，請使用修改功能。"}), 400
        
        # 準備要寫入的數據
        baking = recipe_data.get('baking', {})
        new_recipe = Recipe(
            title=title,
            ingredients=recipe_data.get('ingredients', []), # JSON 欄位
            steps=recipe_data.get('steps', ''),
            top_heat=float(baking.get('topHeat', 0) or 0),
            bottom_heat=float(baking.get('bottomHeat', 0) or 0),
            baking_time=float(baking.get('time', 0) or 0),
            convection=baking.get('convection', False),
            steam=baking.get('steam', False),
            timestamp=datetime.utcnow()
        )

        session.add(new_recipe)
        session.commit()
        
        return jsonify({"status": "success", "message": f"食譜 '{title}' 儲存成功！"})
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": f"儲存失敗: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/api/recipe/<title>', methods=['PUT'])
def update_recipe(title):
    """修改食譜 (DB 更新)。"""
    old_title = title
    recipe_data = request.json
    new_title = recipe_data.get('title')

    if not new_title:
        return jsonify({"status": "error", "message": "新食譜名稱不能為空"}), 400

    session = Session()
    try:
        # 找到舊食譜
        recipe = session.query(Recipe).filter_by(title=old_title).first()
        
        if not recipe:
            return jsonify({"status": "error", "message": f"找不到食譜 '{old_title}'，無法更新。"}), 404

        # 更新欄位
        baking = recipe_data.get('baking', {})
        recipe.title = new_title
        recipe.ingredients = recipe_data.get('ingredients', [])
        recipe.steps = recipe_data.get('steps', '')
        recipe.top_heat = float(baking.get('topHeat', 0) or 0)
        recipe.bottom_heat = float(baking.get('bottomHeat', 0) or 0)
        recipe.baking_time = float(baking.get('time', 0) or 0)
        recipe.convection = baking.get('convection', False)
        recipe.steam = baking.get('steam', False)
        recipe.timestamp = datetime.utcnow()

        session.commit()
        
        return jsonify({"status": "success", "message": f"食譜 '{old_title}' 已更新為 '{new_title}'"})
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": f"更新失敗: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/api/recipe/<title>', methods=['DELETE'])
def delete_recipe(title):
    """刪除食譜 (DB 刪除)。"""
    session = Session()
    try:
        recipe = session.query(Recipe).filter_by(title=title).first()
        
        if recipe:
            session.delete(recipe)
            session.commit()
            return jsonify({"status": "success", "message": f"已刪除食譜：{title}"})
        else:
            return jsonify({"status": "error", "message": f"找不到食譜：{title}"}), 404
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": f"刪除失敗: {str(e)}"}), 500
    finally:
        session.close()
        
# --- 食材資料庫路由 (DB 操作) ---

@app.route('/api/ingredients', methods=['GET'])
def get_ingredients_db():
    """取得食材資料庫 (DB 讀取)。"""
    session = Session()
    try:
        ingredients_db = [i.to_dict() for i in session.query(IngredientDB).all()]
        return jsonify(ingredients_db)
    finally:
        session.close()

@app.route('/api/ingredient', methods=['POST'])
def save_ingredient_db():
    """新增/修改食材資料庫 (DB 寫入)。"""
    ingredient = request.json
    name = ingredient.get('name')
    hydration = ingredient.get('hydration')
    
    if not name or hydration is None:
        return jsonify({"status": "error", "message": "食材名稱和含水率不能為空"}), 400

    session = Session()
    try:
        # 檢查是否已存在 (進行更新)
        item = session.query(IngredientDB).filter_by(name=name).first()
        
        if item:
            item.hydration = float(hydration)
            message = f"已更新食材：{name}"
        else:
            # 否則 (進行新增)
            new_item = IngredientDB(name=name, hydration=float(hydration))
            session.add(new_item)
            message = f"已新增食材：{name}"
        
        session.commit()
        return jsonify({"status": "success", "message": message})
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": f"操作失敗: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/api/ingredient/<name>', methods=['DELETE'])
def delete_ingredient_db(name):
    """刪除食材資料庫中的食材 (DB 刪除)。"""
    session = Session()
    try:
        item = session.query(IngredientDB).filter_by(name=name).first()
        
        if item:
            session.delete(item)
            session.commit()
            return jsonify({"status": "success", "message": f"已刪除食材：{name}"})
        else:
            return jsonify({"status": "error", "message": f"找不到食材：{name}"}), 404
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": f"刪除失敗: {str(e)}"}), 500
    finally:
        session.close()

# --- 統計資訊路由 (DB 讀取) ---

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """取得統計資訊。"""
    session = Session()
    try:
        total_recipes = session.query(Recipe).count()
        total_ingredients_db = session.query(IngredientDB).count()
        
        recipes = session.query(Recipe).all()
        
        # 計算平均總重量
        total_weight_sum = 0
        for recipe in recipes:
            recipe_weight = sum(float(ing.get('weight', 0) or 0) for ing in recipe.ingredients)
            total_weight_sum += recipe_weight
            
        avg_weight = round(total_weight_sum / total_recipes, 1) if total_recipes > 0 else 0
        
        # 尋找最新食譜
        latest_recipe = session.query(Recipe).order_by(Recipe.timestamp.desc()).first()
        latest_recipe_title = latest_recipe.title if latest_recipe else "-"
        
        return jsonify({
            "totalRecipes": total_recipes,
            "totalIngredients": total_ingredients_db,
            "avgWeight": avg_weight,
            "latestRecipe": latest_recipe_title
        })
    finally:
        session.close()

# --- 智能換算路由 (DB 讀取食材資料庫，食譜數據來自 POST body) ---
@app.route('/api/convert', methods=['POST'])
def calculate_conversion_api():
    """計算智能食材換算。"""
    conversion_data = request.json
    recipe = conversion_data.get('recipe')
    new_total_flour = float(conversion_data.get('newTotalFlour', 0) or 0)
    include_non_percentage_groups = conversion_data.get('includeNonPercentageGroups', False)
    
    if not recipe or new_total_flour <= 0:
        return jsonify({ "status": "error", "message": "食譜資料或新麵粉總量無效" }), 400

    session = Session()
    try:
        # 讀取食材資料庫用於識別麵粉和含水率
        ingredients_db_models = session.query(IngredientDB).all()
        ingredients_db = [i.to_dict() for i in ingredients_db_models]
        
        db_dict = {item['name']: item['hydration'] for item in ingredients_db}

        # 輔助函數：判斷是否為麵粉類食材
        def is_main_flour_ingredient(name):
            return any(keyword in name for keyword in ["麵粉", "高筋", "低筋", "全麥", "裸麥"]) and not any(keyword in name for keyword in ["酵母", "泡打粉", "小蘇打", "可可粉", "抹茶粉"])
        
        def is_percentage_group(group_name):
            return not (group_name == "內餡" or group_name == "裝飾")
            
        # 計算原始總麵粉量
        original_total_flour = 0
        for ing in recipe.get('ingredients', []):
            name = ing.get('name', '')
            group = ing.get('group', '')
            weight = float(ing.get('weight', 0) or 0)

            if not is_percentage_group(group):
                continue
                
            hydration_rate = db_dict.get(name)
            is_flour_by_db = hydration_rate is not None and hydration_rate == 0
            is_main_flour = is_main_flour_ingredient(name)
            
            if is_main_flour or is_flour_by_db:
                 original_total_flour += weight

        if original_total_flour <= 0:
            return jsonify({ "status": "error", "message": "此食譜沒有麵粉食材或麵粉重量為0" }), 400
        
        # 計算換算比例
        conversion_ratio = conversion_ratio = new_total_flour / original_total_flour
        
        # 換算所有食材重量
        converted_ingredients = []
        for ing in recipe.get('ingredients', []):
            converted_ing = ing.copy()
            name = converted_ing.get('name', '')
            group = converted_ing.get('group', '')
            original_weight = float(converted_ing.get('weight', 0) or 0)
            
            if is_percentage_group(group) or include_non_percentage_groups:
                if original_weight > 0:
                    converted_ing['weight'] = round(original_weight * conversion_ratio * 10) / 10 
                else:
                    converted_ing['weight'] = 0
            
            converted_ingredients.append(converted_ing)
            
        return jsonify({
            "status": "success",
            "originalTotalFlour": round(original_total_flour, 1),
            "newTotalFlour": round(new_total_flour, 1),
            "conversionRatio": round(conversion_ratio, 3),
            "ingredients": converted_ingredients
        })
    finally:
        session.close()


    
    # Render 環境通常會提供一個 PORT 變數
    port = int(os.environ.get('PORT', 5000))
    # 設置 host='0.0.0.0' 讓應用程式可以被外部網路訪問 (Render 需要)
    app.run(host='0.0.0.0', port=port, debug=True)
# app.py 結尾
# ... (其他函數和路由) ...

def init_db():
    Base.metadata.create_all(engine)

# 確保在 Gunicorn 載入 app.py 模組時執行資料表創建
init_db() 

if __name__ == '__main__':
    # ... (本地啟動邏輯) ...
    pass

