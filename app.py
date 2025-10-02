from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from models import db, Recipe, Ingredient, IngredientDB
from database import init_db
import os
from datetime import datetime
import json

app = Flask(__name__)
CORS(app)

# 資料庫配置
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///recipes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化資料庫
init_db(app)

# 其餘程式碼保持不變...

# 常量定義
PERCENTAGE_GROUPS = ["主麵團", "麵團餡料A", "麵團餡料B", "波蘭種", "液種", "中種", "魯班種"]
FLOUR_CHECK_GROUPS = ["主麵團", "波蘭種", "液種", "中種", "魯班種"]
FLOUR_KEYWORDS = ["高筋麵粉", "中筋麵粉", "低筋麵粉", "全麥麵粉", "裸麥粉", "麵粉"]
BASE_INGREDIENTS = ["高筋麵粉", "中筋麵粉", "低筋麵粉", "全麥麵粉", "裸麥粉", "麵粉", "水", "牛奶", "糖", "鹽", "蜂蜜", "酵母", "泡打粉", "奶油", "鮮奶油", "奶油乳酪", "奶粉", "煉乳", "雞蛋", "優格", "酒", "香草精"]

def is_flour_ingredient(name):
    """檢查是否為麵粉食材"""
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

# API 路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    """取得所有食譜"""
    recipes = Recipe.query.all()
    result = []
    
    for recipe in recipes:
        recipe_data = {
            'title': recipe.title,
            'steps': recipe.steps,
            'timestamp': recipe.created_at.isoformat(),
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
                'weight': ingredient.weight,
                'percent': percent_display,
                'desc': ingredient.description or ""
            })
        
        result.append(recipe_data)
    
    return jsonify(result)

@app.route('/api/recipes', methods=['POST'])
def save_recipe():
    """儲存食譜"""
    data = request.json
    title = data.get('title')
    ingredients_data = data.get('ingredients', [])
    steps = data.get('steps', '')
    baking_info = data.get('baking', {})
    
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

@app.route('/api/recipes/<title>', methods=['DELETE'])
def delete_recipe(title):
    """刪除食譜"""
    recipe = Recipe.query.filter_by(title=title).first()
    if not recipe:
        return jsonify({'status': 'error', 'message': '找不到食譜'}), 404
    
    db.session.delete(recipe)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'已刪除食譜：{title}'})

@app.route('/api/recipes/<old_title>', methods=['PUT'])
def update_recipe(old_title):
    """更新食譜"""
    data = request.json
    new_title = data.get('title')
    ingredients_data = data.get('ingredients', [])
    steps = data.get('steps', '')
    baking_info = data.get('baking', {})
    
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

@app.route('/api/ingredients_db', methods=['GET'])
def get_ingredients_db():
    """取得食材資料庫"""
    ingredients = IngredientDB.query.all()
    result = [{'name': ing.name, 'hydration': ing.hydration} for ing in ingredients]
    return jsonify(result)

@app.route('/api/ingredients_db', methods=['POST'])
def save_ingredient_db():
    """儲存食材到資料庫"""
    data = request.json
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

@app.route('/api/ingredients_db/<name>', methods=['DELETE'])
def delete_ingredient_db(name):
    """刪除食材資料庫中的食材"""
    ingredient = IngredientDB.query.filter_by(name=name).first()
    if not ingredient:
        return jsonify({'status': 'error', 'message': f'找不到食材：{name}'}), 404
    
    db.session.delete(ingredient)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'已刪除食材：{name}'})

@app.route('/api/calculate_conversion', methods=['POST'])
def calculate_conversion():
    """計算食材換算"""
    data = request.json
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
            original_total_flour += ingredient.weight or 0
    
    if original_total_flour <= 0:
        return jsonify({'status': 'error', 'message': '此食譜沒有麵粉食材或麵粉重量為0'}), 400
    
    # 計算換算比例
    conversion_ratio = new_total_flour / original_total_flour
    
    # 換算食材
    converted_ingredients = []
    for ingredient in recipe.ingredients:
        converted_ing = {
            'group': ingredient.group,
            'name': ingredient.name,
            'weight': ingredient.weight,
            'percent': ingredient.percent,
            'desc': ingredient.description or ''
        }
        
        if (ingredient.group in PERCENTAGE_GROUPS or 
            include_non_percentage):
            converted_ing['weight'] = round(ingredient.weight * conversion_ratio, 1)
        
        converted_ingredients.append(converted_ing)
    
    return jsonify({
        'status': 'success',
        'originalTotalFlour': original_total_flour,
        'newTotalFlour': new_total_flour,
        'conversionRatio': conversion_ratio,
        'ingredients': converted_ingredients
    })

if __name__ == '__main__':
    app.run(debug=True)
