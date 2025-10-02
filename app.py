from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
from datetime import datetime
import json

# 設置環境變數
os.environ['PG8000_NATIVE'] = 'false'

from models import db, Recipe, Ingredient, IngredientDB
from database import init_db

app = Flask(__name__)
CORS(app)

# 資料庫配置
database_url = os.environ.get('DATABASE_URL', 'sqlite:///recipes.db')

# 修復 PostgreSQL 連接字串格式
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+pg8000://', 1)
elif database_url and database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+pg8000://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True
}

# 全域變數來儲存資料庫錯誤
db_error = None

try:
    init_db(app)
    print("資料庫初始化成功")
except Exception as e:
    db_error = e
    print(f"資料庫初始化失敗: {e}")

# 常量定義
PERCENTAGE_GROUPS = ["主麵團", "麵團餡料A", "麵團餡料B", "波蘭種", "液種", "中種", "魯班種"]
FLOUR_CHECK_GROUPS = ["主麵團", "波蘭種", "液種", "中種", "魯班種"]
FLOUR_KEYWORDS = ["高筋麵粉", "中筋麵粉", "低筋麵粉", "全麥麵粉", "裸麥粉", "麵粉"]
BASE_INGREDIENTS = ["高筋麵粉", "中筋麵粉", "低筋麵粉", "全麥麵粉", "裸麥粉", "麵粉", "水", "牛奶", "糖", "鹽", "蜂蜜", "酵母", "泡打粉", "奶油", "鮮奶油", "奶油乳酪", "奶粉", "煉乳", "雞蛋", "優格", "酒", "香草精"]

def is_flour_ingredient(name):
    """檢查是否為麵粉食材"""
    if not name:
        return False
    return any(keyword in name for keyword in FLOUR_KEYWORDS)

def normalize_percent_value(p):
    """標準化百分比值"""
    if p is None or p == "":
        return None
    
    if isinstance(p, str):
        p = p.strip()
        if p.endswith('%'):
            p = p[:-1]
        try:
            value = float(p)
            return value / 100 if value > 1 else value
        except ValueError:
            return None
    
    return p / 100 if p > 1 else p

# 根路由 - 根據資料庫狀態返回不同內容
@app.route('/')
def index():
    if db_error:
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h1>資料庫連接錯誤</h1>
                <p>無法連接到資料庫。請檢查資料庫配置。</p>
                <p>錯誤信息: {str(db_error)}</p>
                <p>應用程式仍在運行，但資料庫功能不可用。</p>
            </body>
        </html>
        """, 500
    return render_template('index.html')

# API 路由 - 如果資料庫有錯誤，返回錯誤信息
@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    """取得所有食譜"""
    if db_error:
        return jsonify({'error': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        recipes = Recipe.query.all()
        result = []
        
        for recipe in recipes:
            recipe_data = {
                'title': recipe.title,
                'steps': recipe.steps,
                'timestamp': recipe.created_at.isoformat() if recipe.created_at else "",
                'ingredients': [],
                'baking': {
                    'topHeat': recipe.top_heat,
                    'bottomHeat': recipe.bottom_heat,
                    'time': recipe.baking_time,
                    'convection': recipe.convection,
                    'steam': recipe.steam
                }
            }
            
            for ingredient in recipe.ingredients:
                percent_display = ""
                if ingredient.percent is not None:
                    percent_display = f"{ingredient.percent * 100:.2f}%"
                
                recipe_data['ingredients'].append({
                    'group': ingredient.group,
                    'name': ingredient.name,
                    'weight': float(ingredient.weight) if ingredient.weight else 0,
                    'percent': percent_display,
                    'desc': ingredient.description or ""
                })
            
            result.append(recipe_data)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recipes', methods=['POST'])
def save_recipe():
    """儲存食譜"""
    if db_error:
        return jsonify({'status': 'error', 'message': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': '無效的 JSON 數據'}), 400
            
        title = data.get('title')
        ingredients_data = data.get('ingredients', [])
        steps = data.get('steps', '')
        baking_info = data.get('baking', {})
        
        if not title:
            return jsonify({'status': 'error', 'message': '食譜名稱不能為空'}), 400
        
        # 檢查麵粉食材
        missing_flour_groups = []
        groups_ingredients = {}
        
        for ing in ingredients_data:
            group = ing.get('group')
            if group not in groups_ingredients:
                groups_ingredients[group] = {'has_flour': False, 'ingredients': []}
            
            if is_flour_ingredient(ing.get('name', '')):
                groups_ingredients[group]['has_flour'] = True
        
        for group in FLOUR_CHECK_GROUPS:
            if group in groups_ingredients and not groups_ingredients[group]['has_flour']:
                missing_flour_groups.append(group)
        
        if missing_flour_groups:
            return jsonify({
                'status': 'error',
                'message': f'以下分組必須至少包含一種麵粉食材：{"、".join(missing_flour_groups)}'
            }), 400
        
        # 創建食譜
        recipe = Recipe(
            title=title,
            steps=steps,
            top_heat=baking_info.get('topHeat', 200),
            bottom_heat=baking_info.get('bottomHeat', 200),
            baking_time=baking_info.get('time', 30),
            convection=baking_info.get('convection', False),
            steam=baking_info.get('steam', False)
        )
        
        db.session.add(recipe)
        db.session.flush()  # 獲取 recipe.id
        
        # 添加食材
        for ing_data in ingredients_data:
            ingredient = Ingredient(
                recipe_id=recipe.id,
                group=ing_data.get('group', ''),
                name=ing_data.get('name', ''),
                weight=ing_data.get('weight', 0),
                percent=normalize_percent_value(ing_data.get('percent')),
                description=ing_data.get('desc', '')
            )
            db.session.add(ingredient)
        
        db.session.commit()
        
        return jsonify({'status': 'success', 'message': '食譜儲存成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/recipes/<title>', methods=['DELETE'])
def delete_recipe(title):
    """刪除食譜"""
    if db_error:
        return jsonify({'status': 'error', 'message': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        recipe = Recipe.query.filter_by(title=title).first()
        if not recipe:
            return jsonify({'status': 'error', 'message': '找不到食譜'}), 404
        
        db.session.delete(recipe)
        db.session.commit()
        
        return jsonify({'status': 'success', 'message': f'已刪除食譜：{title}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/recipes/<old_title>', methods=['PUT'])
def update_recipe(old_title):
    """更新食譜"""
    if db_error:
        return jsonify({'status': 'error', 'message': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': '無效的 JSON 數據'}), 400
            
        new_title = data.get('title')
        ingredients_data = data.get('ingredients', [])
        steps = data.get('steps', '')
        baking_info = data.get('baking', {})
        
        if not new_title:
            return jsonify({'status': 'error', 'message': '食譜名稱不能為空'}), 400
        
        # 查找舊食譜
        recipe = Recipe.query.filter_by(title=old_title).first()
        if not recipe:
            return jsonify({'status': 'error', 'message': '找不到食譜'}), 404
        
        # 更新食譜資訊
        recipe.title = new_title
        recipe.steps = steps
        recipe.top_heat = baking_info.get('topHeat', 200)
        recipe.bottom_heat = baking_info.get('bottomHeat', 200)
        recipe.baking_time = baking_info.get('time', 30)
        recipe.convection = baking_info.get('convection', False)
        recipe.steam = baking_info.get('steam', False)
        recipe.created_at = datetime.utcnow()
        
        # 刪除舊食材
        Ingredient.query.filter_by(recipe_id=recipe.id).delete()
        
        # 添加新食材
        for ing_data in ingredients_data:
            ingredient = Ingredient(
                recipe_id=recipe.id,
                group=ing_data.get('group', ''),
                name=ing_data.get('name', ''),
                weight=ing_data.get('weight', 0),
                percent=normalize_percent_value(ing_data.get('percent')),
                description=ing_data.get('desc', '')
            )
            db.session.add(ingredient)
        
        db.session.commit()
        
        return jsonify({'status': 'success', 'message': f'已更新食譜：{old_title} → {new_title}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ingredients_db', methods=['GET'])
def get_ingredients_db():
    """取得食材資料庫"""
    if db_error:
        return jsonify({'error': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        ingredients = IngredientDB.query.all()
        result = [{'name': ing.name, 'hydration': float(ing.hydration) if ing.hydration else 0} for ing in ingredients]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ingredients_db', methods=['POST'])
def save_ingredient_db():
    """儲存食材到資料庫"""
    if db_error:
        return jsonify({'status': 'error', 'message': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': '無效的 JSON 數據'}), 400
            
        name = data.get('name')
        hydration = data.get('hydration')
        
        if not name:
            return jsonify({'status': 'error', 'message': '食材名稱不能為空'}), 400
        
        # 檢查是否已存在
        existing = IngredientDB.query.filter_by(name=name).first()
        if existing:
            existing.hydration = hydration
            message = f'已更新食材：{name}'
        else:
            ingredient = IngredientDB(name=name, hydration=hydration)
            db.session.add(ingredient)
            message = f'已新增食材：{name}'
        
        db.session.commit()
        return jsonify({'status': 'success', 'message': message})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ingredients_db/<name>', methods=['DELETE'])
def delete_ingredient_db(name):
    """刪除食材資料庫中的食材"""
    if db_error:
        return jsonify({'status': 'error', 'message': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        ingredient = IngredientDB.query.filter_by(name=name).first()
        if not ingredient:
            return jsonify({'status': 'error', 'message': f'找不到食材：{name}'}), 404
        
        db.session.delete(ingredient)
        db.session.commit()
        
        return jsonify({'status': 'success', 'message': f'已刪除食材：{name}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/calculate_conversion', methods=['POST'])
def calculate_conversion():
    """計算食材換算"""
    if db_error:
        return jsonify({'status': 'error', 'message': f'資料庫連接錯誤: {str(db_error)}'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': '無效的 JSON 數據'}), 400
            
        recipe_title = data.get('recipeTitle')
        new_total_flour = data.get('newTotalFlour')
        include_non_percentage = data.get('includeNonPercentage', False)
        
        # 查找食譜
        recipe = Recipe.query.filter_by(title=recipe_title).first()
        if not recipe:
            return jsonify({'status': 'error', 'message': '找不到指定的食譜'}), 404
        
        # 計算原始總麵粉量
        original_total_flour = 0
        for ingredient in recipe.ingredients:
            if (is_flour_ingredient(ingredient.name) and 
                ingredient.group in PERCENTAGE_GROUPS):
                original_total_flour += float(ingredient.weight) if ingredient.weight else 0
        
        if original_total_flour <= 0:
            return jsonify({'status': 'error', 'message': '此食譜沒有麵粉食材或麵粉重量為0'}), 400
        
        # 計算換算比例
        conversion_ratio = float(new_total_flour) / original_total_flour
        
        # 換算食材
        converted_ingredients = []
        for ingredient in recipe.ingredients:
            original_weight = float(ingredient.weight) if ingredient.weight else 0
            new_weight = original_weight
            
            if (ingredient.group in PERCENTAGE_GROUPS or 
                include_non_percentage):
                new_weight = round(original_weight * conversion_ratio, 1)
            
            converted_ingredients.append({
                'group': ingredient.group,
                'name': ingredient.name,
                'weight': new_weight,
                'originalWeight': original_weight,
                'percent': ingredient.percent,
                'desc': ingredient.description or ''
            })
        
        return jsonify({
            'status': 'success',
            'originalTotalFlour': original_total_flour,
            'newTotalFlour': float(new_total_flour),
            'conversionRatio': conversion_ratio,
            'ingredients': converted_ingredients
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health')
def health_check():
    """健康檢查端點"""
    if db_error:
        return jsonify({'status': 'unhealthy', 'database': 'disconnected', 'error': str(db_error)}), 500
    else:
        try:
            # 嘗試連接資料庫
            db.session.execute('SELECT 1')
            return jsonify({'status': 'healthy', 'database': 'connected'})
        except Exception as e:
            return jsonify({'status': 'unhealthy', 'database': 'disconnected', 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=os.environ.get('DEBUG', False), host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
