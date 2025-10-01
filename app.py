from flask import Flask, request, jsonify, render_template
import json
import os
from datetime import datetime
from urllib.parse import unquote

# -----------------
# 應用程式設定
# -----------------
app = Flask(__name__, template_folder='.') # 讓 Flask 在當前目錄尋找 index.html
DATA_FILE = 'data.json' # 用於資料持久化的檔案

# -----------------
# 輔助函數 (資料庫操作)
# -----------------

def load_db():
    """從 JSON 檔案載入食譜和食材資料庫。"""
    if not os.path.exists(DATA_FILE):
        return {
            'recipes': [],
            'ingredients_db': []
        }
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 確保資料結構完整，即使檔案內容不完整
            return {
                'recipes': data.get('recipes', []),
                'ingredients_db': data.get('ingredients_db', [])
            }
    except (json.JSONDecodeError, FileNotFoundError):
        # 修正：確保在檔案損壞或找不到時返回有效的空結構
        return {
            'recipes': [],
            'ingredients_db': []
        }

def save_db(data):
    """將食譜和食材資料庫存入 JSON 檔案。"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# -----------------
# 輔助函數 (食譜處理邏輯 - 繼承自 code.gs)
# -----------------

def get_recipes_logic(db):
    """
    從資料庫中取得食譜資料並整理成前端需要的格式。
    (與 code.gs 的 getRecipes 邏輯相似)
    """
    
    # 由於我們現在的資料結構是 JSON 列表，不需要像 Apps Script 那樣從扁平化表格重建
    recipes = db.get('recipes', [])
    
    # 確保百分比是小數（在保存時應該已經是小數）
    for recipe in recipes:
        for ing in recipe['ingredients']:
            if isinstance(ing['percent'], str):
                try:
                    ing['percent'] = float(ing['percent'].replace('%', '')) / 100
                except:
                    ing['percent'] = 0.0
            elif ing['percent'] is None:
                ing['percent'] = 0.0
    
    return recipes


def get_stats_logic(db):
    """
    計算食譜統計數據。
    (與 code.gs 的 getStats 邏輯相似)
    """
    recipes = get_recipes_logic(db) # 使用整理後的食譜列表

    # 【修正】: 處理無資料情況
    if not recipes:
        return { 
            'totalRecipes': 0, 
            'totalIngredients': 0, 
            'avgWeight': 0, 
            'latestRecipe': '無' 
        }

    total_ingredients = 0
    total_weight = 0
    
    for recipe in recipes:
        total_ingredients += len(recipe['ingredients'])
        for ing in recipe['ingredients']:
            total_weight += float(ing.get('weight', 0) or 0)
    
    avg_weight = total_weight / total_ingredients if total_ingredients > 0 else 0
    
    # 根據時間戳記找到最新的食譜
    latest_recipe = max(recipes, key=lambda r: datetime.fromisoformat(r['timestamp']) if r.get('timestamp') else datetime.min)
    
    return {
        'totalRecipes': len(recipes),
        'totalIngredients': total_ingredients,
        'avgWeight': avg_weight,
        'latestRecipe': latest_recipe['title']
    }

def save_recipe_logic(db, data):
    """
    儲存或更新食譜。
    (與 code.gs 的 saveRecipe 邏輯相似)
    """
    title = data.get('title')
    ingredients = data.get('ingredients')
    steps = data.get('steps')
    baking_info = data.get('bakingInfo')
    is_update = data.get('isUpdate', False)
    original_title = data.get('originalTitle')
    
    if not title or not ingredients:
        return {'status': 'error', 'message': '食譜名稱或食材不可為空。'}

    # 處理前端傳來的百分比字串 (例如: "50%")
    processed_ingredients = []
    for ing in ingredients:
        percent_value = 0.0
        p_str = ing.get('percent', '')
        if isinstance(p_str, str) and p_str.endswith('%'):
            try:
                percent_value = float(p_str.replace('%', '')) / 100
            except ValueError:
                percent_value = 0.0
        
        processed_ingredients.append({
            'group': ing.get('group', ''),
            'name': ing.get('name', ''),
            'weight': float(ing.get('weight') or 0),
            'percent': percent_value, # 儲存為小數
            'desc': ing.get('desc', '')
        })

    new_recipe = {
        'title': title,
        'ingredients': processed_ingredients,
        'steps': steps,
        'timestamp': datetime.now().isoformat(),
        'baking': baking_info
    }
    
    recipes = db['recipes']
    
    if is_update:
        # 刪除舊紀錄（根據原始標題 original_title）
        db['recipes'] = [r for r in recipes if r['title'] != original_title]
        # 如果新標題與舊標題不同，確保新標題沒有重複
        if title != original_title and any(r['title'] == title for r in db['recipes']):
             # 如果新標題與其他現有食譜重複，則不儲存
             db['recipes'] = recipes # 恢復原始列表
             return {'status': 'error', 'message': f'食譜名稱「{title}」已存在。'}
    elif any(r['title'] == title for r in recipes):
        return {'status': 'error', 'message': f'食譜名稱「{title}」已存在。'}

    # 新增或更新紀錄
    db['recipes'].append(new_recipe)
    save_db(db)
    
    return {'status': 'success', 'message': f'食譜「{title}」已成功{"更新" if is_update else "儲存"}！'}


# -----------------
# Flask 路由 (API Endpoints)
# -----------------

@app.route('/')
def index():
    """主頁路由，渲染 index.html"""
    return render_template('index.html')


@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    """獲取所有食譜"""
    db = load_db()
    recipes = get_recipes_logic(db)
    return jsonify(recipes)


@app.route('/api/recipe', methods=['POST'])
def save_recipe():
    """儲存或更新食譜"""
    data = request.get_json()
    db = load_db()
    result = save_recipe_logic(db, data)
    
    if result['status'] == 'error':
        return jsonify(result), 400
    return jsonify(result)


@app.route('/api/recipe/<recipe_name>', methods=['DELETE'])
def delete_recipe(recipe_name):
    """刪除食譜"""
    # URL 編碼後的名稱需要解碼
    decoded_name = unquote(recipe_name)
    db = load_db()
    
    recipes = db['recipes']
    
    if any(r['title'] == decoded_name for r in recipes):
        db['recipes'] = [r for r in recipes if r['title'] != decoded_name]
        save_db(db)
        return jsonify({'status': 'success', 'message': f'食譜「{decoded_name}」已成功刪除！'})
    
    return jsonify({'status': 'error', 'message': f'找不到食譜「{decoded_name}」'}), 404


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """獲取統計數據"""
    db = load_db()
    stats = get_stats_logic(db)
    return jsonify(stats)


@app.route('/api/ingredientsdb', methods=['GET'])
def get_ingredients_db():
    """獲取自訂食材資料庫"""
    db = load_db()
    # 【修正】: 確保返回 []
    return jsonify(db.get('ingredients_db', []))


@app.route('/api/ingredientsdb', methods=['POST'])
def save_custom_ingredient():
    """儲存或更新自訂食材"""
    data = request.get_json()
    name = data.get('name')
    hydration = data.get('hydration')
    
    if not name or hydration is None:
        return jsonify({'status': 'error', 'message': '請提供有效的食材名稱和含水率'}), 400

    db = load_db()
    ingredients_db = db['ingredients_db']
    
    # 檢查是否已存在
    found = next((ing for ing in ingredients_db if ing['name'] == name), None)
    
    if found:
        # 更新
        found['hydration'] = float(hydration)
        message = f'自訂食材「{name}」含水率已更新！'
    else:
        # 新增
        ingredients_db.append({'name': name, 'hydration': float(hydration)})
        message = f'自訂食材「{name}」已新增！'
        
    save_db(db)
    return jsonify({'status': 'success', 'message': message})


@app.route('/api/ingredientsdb/<name>', methods=['DELETE'])
def delete_custom_ingredient(name):
    """刪除自訂食材"""
    decoded_name = unquote(name)
    db = load_db()
    
    original_count = len(db['ingredients_db'])
    db['ingredients_db'] = [ing for ing in db['ingredients_db'] if ing['name'] != decoded_name]
    
    if len(db['ingredients_db']) < original_count:
        save_db(db)
        return jsonify({'status': 'success', 'message': f'自訂食材「{decoded_name}」已成功刪除！'})
    
    return jsonify({'status': 'error', 'message': f'找不到名為「{decoded_name}」的自訂食材'}), 404

@app.route('/api/conversion', methods=['POST'])
def calculate_conversion():
    """智能換算工具"""
    data = request.get_json()
    recipe_name = data.get('recipeName')
    new_total_flour = data.get('newTotalFlour')
    include_non_percentage_groups = data.get('includeNonPercentageGroups')

    if not recipe_name or not new_total_flour:
        return jsonify({'status': 'error', 'message': '缺少食譜名稱或目標麵粉總量'}), 400

    db = load_db()
    recipes = get_recipes_logic(db)
    recipe = next((r for r in recipes if r['title'] == recipe_name), None)

    if not recipe:
        return jsonify({'status': 'error', 'message': '找不到指定的食譜'}), 404

    is_flour_ingredient = lambda name: name and ('麵粉' in name or '粉' in name)
    is_percentage_group = lambda group: group in ['中種', '主麵團', '主面团', '中种', '液種', '湯種']

    # 計算原始總麵粉量
    original_total_flour = 0
    for ing in recipe['ingredients']:
        if is_flour_ingredient(ing['name']) and is_percentage_group(ing['group']):
            original_total_flour += float(ing.get('weight', 0) or 0)
    
    if original_total_flour <= 0:
        return jsonify({'status': 'error', 'message': '此食譜沒有用於百分比計算的麵粉食材或麵粉重量為0'}), 400
    
    # 計算換算比例
    conversion_ratio = float(new_total_flour) / original_total_flour
    
    # 換算所有食材重量
    converted_ingredients = []
    for ing in recipe['ingredients']:
        converted_ing = ing.copy()
        
        # 只有在百分比分組中的食材才進行換算，或者如果用戶選擇包含非百分比分組
        if is_percentage_group(ing['group']) or include_non_percentage_groups:
            original_weight = float(ing.get('weight', 0) or 0)
            # 四捨五入到小數點後一位
            converted_ing['weight'] = round(original_weight * conversion_ratio * 10) / 10
        
        converted_ingredients.append(converted_ing)
    
    return jsonify({
        'status': 'success',
        'originalTotalFlour': original_total_flour,
        'newTotalFlour': float(new_total_flour),
        'conversionRatio': conversion_ratio,
        'ingredients': converted_ingredients
    })


if __name__ == '__main__':
    # 確保首次運行時存在 data.json
    if not os.path.exists(DATA_FILE):
        save_db(load_db()) # 寫入初始空結構
    # 運行 Flask 應用
    # 在實際部署中，您會使用 Gunicorn/uWSGI 等 WSGI 伺服器
    app.run(debug=True)
