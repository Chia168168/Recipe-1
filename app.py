# app.py
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import json
import os
import re

app = Flask(__name__)
DATA_FILE = 'data.json'

# --- 數據初始化與儲存函數 (取代 Apps Script 的 Google Sheets 讀寫) ---
def load_data():
    """載入食譜和食材資料庫數據。"""
    if not os.path.exists(DATA_FILE):
        return {"recipes": [], "ingredients_db": []}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # 如果檔案損壞，返回空數據
            return {"recipes": [], "ingredients_db": []}

def save_data(data):
    """儲存食譜和食材資料庫數據。"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 輔助函數 (從 code.gs 移植並轉換為 Python) ---

def normalize_percent_value(p):
    """標準化百分比值 (從 Apps Script 移植)。"""
    if p is None or p == "":
        return ""
    
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
    """計算含水率。"""
    flour_total = 0
    water_total = 0
    
    # 標準化食材名稱以利查找
    db_dict = {item['name']: item['hydration'] for item in ingredients_db}
    
    # 常用麵粉/水/蛋等關鍵字判斷 (這裡使用簡化的邏輯)
    def is_flour(name):
        return any(keyword in name for keyword in ["麵粉", "高筋", "低筋", "全麥", "粉"])
    def is_water(name):
        return any(keyword in name for keyword in ["水", "牛奶", "液", "汁"])
    def is_egg(name):
        return "蛋" in name
    
    for ing in ingredients:
        weight = float(ing.get('weight', 0) or 0)
        name = ing.get('name', '')
        group = ing.get('group', '')
        
        if weight <= 0:
            continue

        # 檢查是否為百分比分組
        if not is_percentage_group(group):
            continue

        # 查找自訂含水率
        hydration_rate = db_dict.get(name)
        
        # 處理含水率邏輯
        if hydration_rate is not None and hydration_rate != "":
            # 使用自訂含水率計算麵粉和水
            hydration_rate = float(hydration_rate)
            if hydration_rate > 100: hydration_rate = 100
            
            # 假設重量中 (100-rate)% 是乾物質(麵粉), rate% 是水
            # 這是烘焙中處理自訂食材的常見簡化方式
            # 只有當含水率不為 0 或 100 時才分配
            if hydration_rate > 0 and hydration_rate < 100:
                water_equivalent = weight * (hydration_rate / 100.0)
                flour_equivalent = weight * ((100.0 - hydration_rate) / 100.0)
                flour_total += flour_equivalent
                water_total += water_equivalent
                
            elif hydration_rate == 0: # 視為純麵粉 (乾性材料)
                flour_total += weight
            elif hydration_rate == 100: # 視為純水 (濕性材料)
                water_total += weight
                
        # 處理標準麵粉和水 (如果沒有自訂含水率)
        elif is_flour(name):
            flour_total += weight
        elif is_water(name):
            water_total += weight
        elif is_egg(name):
            # 假設全蛋含水率約 75%
            water_total += weight * 0.75
            
    if flour_total > 0:
        hydration = (water_total / flour_total) * 100
        return f"{hydration:.2f}%"
    else:
        return "0%"

def is_percentage_group(group_name):
    """判斷是否為計算百分比的分組。"""
    # 根據原 Apps Script 邏輯，需要計算百分比的分組通常是主麵團、中種、湯種等，
    # 但不會是餡料或裝飾。這裡沿用 Apps Script 的處理邏輯。
    group_name = group_name.strip()
    return not (group_name == "內餡" or group_name == "裝飾")

def is_flour_ingredient(name):
    """判斷是否為麵粉類食材。"""
    return any(keyword in name for keyword in ["麵粉", "高筋", "低筋", "全麥", "粉"])

# --- API 路由 (取代 Apps Script 的 function calls) ---

@app.route('/', methods=['GET'])
def serve_index():
    """根路由：提供 index.html 內容。"""
    # 直接使用 Flask 的 render_template_string 來呈現 index.html 的內容
    # 在實際部署時，通常會用 render_template('index.html')
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    """取得所有食譜列表 (取代 getRecipes)。"""
    data = load_data()
    
    # 這裡的數據已經是以食譜為單位，不需要像 Apps Script 那樣從多行食材數據組裝
    recipes_list = data.get('recipes', [])

    # 為每個食譜計算含水率，因為前端需要顯示
    ingredients_db = data.get('ingredients_db', [])
    for recipe in recipes_list:
        recipe['hydration'] = calculate_hydration(recipe.get('ingredients', []), ingredients_db)
        # 確保 baking 鍵存在
        if 'baking' not in recipe:
            recipe['baking'] = {}
        # 確保 timestamp 存在且是字串
        if 'timestamp' in recipe and isinstance(recipe['timestamp'], datetime):
             recipe['timestamp'] = recipe['timestamp'].isoformat()
        
    return jsonify(recipes_list)

@app.route('/api/recipe', methods=['POST'])
def save_recipe():
    """新增食譜 (取代 saveRecipe)。"""
    recipe_data = request.json
    title = recipe_data.get('title')
    
    if not title:
        return jsonify({"status": "error", "message": "食譜名稱不能為空"}), 400

    data = load_data()
    recipes = data['recipes']
    
    # 檢查食譜是否已存在（用於防止重複儲存，雖然通常修改是走 PUT/updateRecipe）
    if any(r['title'] == title for r in recipes):
         return jsonify({"status": "error", "message": f"食譜 '{title}' 已存在，請使用修改功能。"}), 400
    
    # 格式化數據
    new_recipe = {
        'title': title,
        'ingredients': recipe_data.get('ingredients', []),
        'steps': recipe_data.get('steps', ''),
        'baking': recipe_data.get('baking', {}),
        'timestamp': datetime.now().isoformat()
    }

    # 處理食材百分比的數值轉換（Flask 後端保留原始百分比字串，方便前端顯示）
    for ing in new_recipe['ingredients']:
        # 確保 percent 是字串格式 (e.g. "50.00%")
        if 'percent' in ing and isinstance(ing['percent'], (int, float)):
            ing['percent'] = f"{ing['percent']:.2f}%"

    recipes.append(new_recipe)
    save_data(data)
    
    return jsonify({"status": "success", "message": f"食譜 '{title}' 儲存成功！"})

@app.route('/api/recipe/<title>', methods=['PUT'])
def update_recipe(title):
    """修改食譜 (取代 updateRecipe)。"""
    old_title = title
    recipe_data = request.json
    new_title = recipe_data.get('title')
    
    if not new_title:
        return jsonify({"status": "error", "message": "新食譜名稱不能為空"}), 400

    data = load_data()
    recipes = data['recipes']
    
    # 1. 刪除舊食譜 (Apps Script 的做法)
    original_len = len(recipes)
    data['recipes'] = [r for r in recipes if r['title'] != old_title]
    deleted_count = original_len - len(data['recipes'])

    if deleted_count == 0:
        # 如果舊食譜不存在，但用戶嘗試更新，可以視為新增
        pass # 繼續下一步的新增操作

    # 2. 新增修改後的食譜
    new_recipe = {
        'title': new_title,
        'ingredients': recipe_data.get('ingredients', []),
        'steps': recipe_data.get('steps', ''),
        'baking': recipe_data.get('baking', {}),
        'timestamp': datetime.now().isoformat()
    }
    
    # 處理食材百分比的數值轉換
    for ing in new_recipe['ingredients']:
        if 'percent' in ing and isinstance(ing['percent'], (int, float)):
            ing['percent'] = f"{ing['percent']:.2f}%"

    data['recipes'].append(new_recipe)
    save_data(data)
    
    return jsonify({"status": "success", "message": f"食譜 '{old_title}' 已更新為 '{new_title}'"})

@app.route('/api/recipe/<title>', methods=['DELETE'])
def delete_recipe(title):
    """刪除食譜 (取代 deleteRecipe)。"""
    data = load_data()
    original_len = len(data['recipes'])
    
    data['recipes'] = [r for r in data['recipes'] if r['title'] != title]
    
    deleted_count = original_len - len(data['recipes'])
    
    if deleted_count > 0:
        save_data(data)
        return jsonify({"status": "success", "message": f"已刪除食譜：{title} ({deleted_count} 行數據)"})
    else:
        return jsonify({"status": "error", "message": f"找不到食譜：{title}"}), 404

# --- 食材資料庫路由 (取代 getIngredientsDB, saveIngredientDB, deleteIngredientDB) ---

@app.route('/api/ingredients', methods=['GET'])
def get_ingredients_db():
    """取得食材資料庫 (取代 getIngredientsDB)。"""
    data = load_data()
    return jsonify(data.get('ingredients_db', []))

@app.route('/api/ingredient', methods=['POST'])
def save_ingredient_db():
    """新增/修改食材資料庫 (取代 saveIngredientDB)。"""
    ingredient = request.json
    name = ingredient.get('name')
    hydration = ingredient.get('hydration')
    
    if not name or hydration is None:
        return jsonify({"status": "error", "message": "食材名稱和含水率不能為空"}), 400

    data = load_data()
    ingredients_db = data['ingredients_db']
    
    updated = False
    for item in ingredients_db:
        if item['name'] == name:
            item['hydration'] = hydration
            updated = True
            break
            
    if not updated:
        ingredients_db.append({'name': name, 'hydration': hydration})
        message = f"已新增食材：{name}"
    else:
        message = f"已更新食材：{name}"
    
    save_data(data)
    return jsonify({"status": "success", "message": message})

@app.route('/api/ingredient/<name>', methods=['DELETE'])
def delete_ingredient_db(name):
    """刪除食材資料庫中的食材 (取代 deleteIngredientDB)。"""
    data = load_data()
    ingredients_db = data['ingredients_db']
    
    original_len = len(ingredients_db)
    
    data['ingredients_db'] = [item for item in ingredients_db if item['name'] != name]
    
    deleted_count = original_len - len(data['ingredients_db'])
    
    if deleted_count > 0:
        save_data(data)
        return jsonify({"status": "success", "message": f"已刪除食材：{name}"})
    else:
        return jsonify({"status": "error", "message": f"找不到食材：{name}"}), 404

# --- 統計資訊路由 (取代 getStats) ---

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """取得統計資訊 (取代 getStats)。"""
    data = load_data()
    recipes = data.get('recipes', [])
    ingredients_db = data.get('ingredients_db', [])
    
    total_recipes = len(recipes)
    total_ingredients_db = len(ingredients_db)
    
    # 計算所有食譜的平均總重量
    total_weight_sum = 0
    total_recipe_count = 0
    for recipe in recipes:
        recipe_weight = sum(float(ing.get('weight', 0) or 0) for ing in recipe.get('ingredients', []))
        total_weight_sum += recipe_weight
        total_recipe_count += 1
        
    avg_weight = round(total_weight_sum / total_recipe_count, 1) if total_recipe_count > 0 else 0
    
    # 尋找最新食譜
    latest_recipe_title = "-"
    if recipes:
        # 確保 timestamp 是可以比較的
        sorted_recipes = sorted(recipes, key=lambda r: r.get('timestamp', '1970-01-01T00:00:00'), reverse=True)
        latest_recipe_title = sorted_recipes[0]['title']
        
    return jsonify({
        "totalRecipes": total_recipes,
        "totalIngredients": total_ingredients_db,
        "avgWeight": avg_weight,
        "latestRecipe": latest_recipe_title
    })
    
# --- 智能換算路由 (取代 calculateConversion) ---
@app.route('/api/convert', methods=['POST'])
def calculate_conversion_api():
    """計算智能食材換算 (取代 calculateConversion)。"""
    conversion_data = request.json
    recipe = conversion_data.get('recipe')
    new_total_flour = float(conversion_data.get('newTotalFlour', 0) or 0)
    include_non_percentage_groups = conversion_data.get('includeNonPercentageGroups', False)
    
    if not recipe or new_total_flour <= 0:
        return jsonify({ "status": "error", "message": "食譜資料或新麵粉總量無效" }), 400

    # 取得食材資料庫用於識別麵粉和含水率
    data = load_data()
    ingredients_db = data.get('ingredients_db', [])

    # 查找自訂含水率
    db_dict = {item['name']: item['hydration'] for item in ingredients_db}

    # 輔助函數：判斷是否為麵粉類食材（使用更精確的判斷，排除像麵包粉、泡打粉等非主要麵粉）
    def is_main_flour_ingredient(name):
        return any(keyword in name for keyword in ["麵粉", "高筋", "低筋", "全麥", "裸麥"]) and not any(keyword in name for keyword in ["酵母", "泡打粉", "小蘇打", "可可粉", "抹茶粉"])
        
    # 計算原始總麵粉量
    original_total_flour = 0
    for ing in recipe.get('ingredients', []):
        name = ing.get('name', '')
        group = ing.get('group', '')
        weight = float(ing.get('weight', 0) or 0)

        # 1. 必須是百分比分組
        if not is_percentage_group(group):
            continue
            
        # 2. 必須是麵粉類食材或含水率為 0 的乾性材料
        hydration_rate = db_dict.get(name)
        
        is_flour_by_db = hydration_rate is not None and hydration_rate == 0
        is_main_flour = is_main_flour_ingredient(name)
        
        if is_main_flour or is_flour_by_db:
             original_total_flour += weight

    if original_total_flour <= 0:
        return jsonify({ "status": "error", "message": "此食譜沒有麵粉食材或麵粉重量為0" }), 400
    
    # 計算換算比例
    conversion_ratio = new_total_flour / original_total_flour
    
    # 換算所有食材重量
    converted_ingredients = []
    for ing in recipe.get('ingredients', []):
        converted_ing = ing.copy()
        
        name = converted_ing.get('name', '')
        group = converted_ing.get('group', '')
        original_weight = float(converted_ing.get('weight', 0) or 0)
        
        # 只有在百分比分組中的食材才進行換算，或者如果用戶選擇包含非百分比分組
        if is_percentage_group(group) or include_non_percentage_groups:
            if original_weight > 0:
                converted_ing['weight'] = round(original_weight * conversion_ratio * 10) / 10 # 四捨五入到小數點後一位
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

if __name__ == '__main__':
    # 確保 data.json 存在
    if not os.path.exists(DATA_FILE):
        save_data({"recipes": [], "ingredients_db": []})

    # 執行以下指令來啟動 Flask 伺服器:
    # python app.py
    # 伺服器將在 http://127.0.0.1:5000/ 運行
    app.run(debug=True)
