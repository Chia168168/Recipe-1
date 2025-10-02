# app.py

import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import io
import xlsxwriter

app = Flask(__name__)
CORS(app)

# Database connection
def get_db_connection():
    conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=RealDictCursor)
    return conn

# Initialize database tables
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            group_name TEXT,
            ingredient TEXT,
            weight FLOAT,
            percent FLOAT,
            description TEXT,
            steps TEXT,
            timestamp TIMESTAMP,
            top_heat INTEGER,
            bottom_heat INTEGER,
            bake_time INTEGER,
            convection BOOLEAN,
            steam BOOLEAN
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ingredients_db (
            name TEXT PRIMARY KEY,
            hydration FLOAT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# Normalize percent value
def normalize_percent_value(p):
    if p is None or p == "":
        return None
    if isinstance(p, str):
        s = p.strip()
        if s.endswith('%'):
            try:
                n = float(s.replace('%', '').strip())
                return n / 100
            except ValueError:
                return None
        try:
            n = float(s)
            return n / 100 if n > 1 else n
        except ValueError:
            return None
    if isinstance(p, (int, float)):
        return p / 100 if p > 1 else p
    return None

# Get ingredients DB
@app.route('/api/ingredients_db', methods=['GET'])
def get_ingredients_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ingredients_db")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(data)

# Save ingredient DB
@app.route('/api/save_ingredient_db', methods=['POST'])
def save_ingredient_db():
    ingredient = request.json
    name = ingredient['name']
    hydration = ingredient['hydration']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ingredients_db (name, hydration) VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE SET hydration = %s
    """, (name, hydration, hydration))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success", "message": f"已更新食材：{name}" if 'updated' else f"已新增食材：{name}"})

# Delete ingredient DB
@app.route('/api/delete_ingredient_db', methods=['DELETE'])
def delete_ingredient_db():
    name = request.args.get('name')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM ingredients_db WHERE name = %s", (name,))
    conn.commit()
    if cur.rowcount == 0:
        return jsonify({"status": "error", "message": f"找不到食材：{name}"}), 404
    cur.close()
    conn.close()
    return jsonify({"status": "success", "message": f"已刪除食材：{name}"})

# Save recipe
@app.route('/api/save_recipe', methods=['POST'])
def save_recipe():
    data = request.json
    title = data['title']
    ingredients = data['ingredients']
    steps = data['steps']
    baking_info = data['bakingInfo']
    timestamp = datetime.now()

    conn = get_db_connection()
    cur = conn.cursor()
    for ing in ingredients:
        percent_norm = normalize_percent_value(ing['percent'])
        cur.execute("""
            INSERT INTO recipes (title, group_name, ingredient, weight, percent, description, steps, timestamp,
                                 top_heat, bottom_heat, bake_time, convection, steam)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (title, ing['group'], ing['name'], ing['weight'], percent_norm, ing['desc'], steps, timestamp,
              baking_info['topHeat'], baking_info['bottomHeat'], baking_info['time'],
              baking_info['convection'], baking_info['steam']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

# Get recipes
@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM recipes ORDER BY timestamp DESC")
    data = cur.fetchall()
    cur.close()
    conn.close()

    recipes = {}
    for row in data:
        title = row['title']
        if title not in recipes:
            recipes[title] = {
                "title": title,
                "ingredients": [],
                "steps": row['steps'],
                "timestamp": row['timestamp'].isoformat() if row['timestamp'] else "",
                "baking": {
                    "topHeat": row['top_heat'] or 200,
                    "bottomHeat": row['bottom_heat'] or 200,
                    "time": row['bake_time'] or 30,
                    "convection": row['convection'],
                    "steam": row['steam']
                }
            }
        percent_display = ""
        if row['percent'] is not None:
            percent_display = f"{row['percent'] * 100:.2f}%"
        recipes[title]['ingredients'].append({
            "group": row['group_name'] or "",
            "name": row['ingredient'] or "",
            "weight": row['weight'] or 0,
            "percent": percent_display,
            "desc": row['description'] or ""
        })
    return jsonify(list(recipes.values()))

# Delete recipe
@app.route('/api/delete_recipe', methods=['DELETE'])
def delete_recipe():
    title = request.args.get('title')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM recipes WHERE title = %s", (title,))
    deleted_count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success", "message": f"已刪除食譜：{title} ({deleted_count} 行數據)"})

# Update recipe
@app.route('/api/update_recipe', methods=['POST'])
def update_recipe():
    data = request.json
    old_title = data['oldTitle']
    new_title = data['newTitle']
    ingredients = data['ingredients']
    steps = data['steps']
    baking_info = data['bakingInfo']
    timestamp = datetime.now()

    conn = get_db_connection()
    cur = conn.cursor()
    # Delete old
    cur.execute("DELETE FROM recipes WHERE title = %s", (old_title,))
    deleted_count = cur.rowcount
    # Insert new
    for ing in ingredients:
        percent_norm = normalize_percent_value(ing['percent'])
        cur.execute("""
            INSERT INTO recipes (title, group_name, ingredient, weight, percent, description, steps, timestamp,
                                 top_heat, bottom_heat, bake_time, convection, steam)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (new_title, ing['group'], ing['name'], ing['weight'], percent_norm, ing['desc'], steps, timestamp,
              baking_info['topHeat'], baking_info['bottomHeat'], baking_info['time'],
              baking_info['convection'], baking_info['steam']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success", "message": f"已更新食譜：{old_title} → {new_title} (刪除 {deleted_count} 行，新增 {len(ingredients)} 行)"})

# Diagnose data structure (for debugging)
@app.route('/api/diagnose', methods=['GET'])
def diagnose_data_structure():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM recipes LIMIT 5")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(data)

# Clear all data (caution)
@app.route('/api/clear_all', methods=['DELETE'])
def clear_all_data():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM recipes")
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "已清除所有數據"})

# Calculate recipe conversion
@app.route('/api/calculate_conversion', methods=['POST'])
def calculate_recipe_conversion():
    data = request.json
    recipe_title = data['recipeTitle']
    new_total_flour = data['newTotalFlour']
    include_non_percentage_groups = data['includeNonPercentageGroups']

    # Get recipe
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM recipes WHERE title = %s", (recipe_title,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return jsonify({"status": "error", "message": "找不到指定的食譜"}), 404

    # Build recipe object
    recipe = {
        "title": recipe_title,
        "ingredients": [],
        "steps": rows[0]['steps'],
        "baking": {
            "topHeat": rows[0]['top_heat'],
            "bottomHeat": rows[0]['bottom_heat'],
            "time": rows[0]['bake_time'],
            "convection": rows[0]['convection'],
            "steam": rows[0]['steam']
        }
    }
    for row in rows:
        percent_display = f"{row['percent'] * 100:.2f}%" if row['percent'] is not None else ""
        recipe['ingredients'].append({
            "group": row['group_name'] or "",
            "name": row['ingredient'] or "",
            "weight": row['weight'] or 0,
            "percent": percent_display,
            "desc": row['description'] or ""
        })

    # Calculate original total flour
    original_total_flour = 0
    for ing in recipe['ingredients']:
        if is_flour_ingredient(ing['name']) and is_percentage_group(ing['group']):
            original_total_flour += ing['weight']

    if original_total_flour <= 0:
        return jsonify({"status": "error", "message": "此食譜沒有麵粉食材或麵粉重量為0"}), 400

    conversion_ratio = new_total_flour / original_total_flour

    converted_ingredients = []
    for ing in recipe['ingredients']:
        converted_ing = ing.copy()
        if is_percentage_group(ing['group']) or include_non_percentage_groups:
            converted_ing['weight'] = round(ing['weight'] * conversion_ratio, 1)
        converted_ingredients.append(converted_ing)

    return jsonify({
        "status": "success",
        "originalTotalFlour": original_total_flour,
        "newTotalFlour": new_total_flour,
        "conversionRatio": conversion_ratio,
        "ingredients": converted_ingredients,
        "recipe": recipe
    })

def is_flour_ingredient(ingredient_name):
    flour_keywords = ["高筋麵粉", "中筋麵粉", "低筋麵粉", "全麥麵粉", "裸麥粉", "麵粉"]
    return any(keyword in ingredient_name for keyword in flour_keywords)

def is_percentage_group(group_name):
    percentage_groups = ["主麵團", "麵團餡料A", "麵團餡料B", "波蘭種", "液種", "中種", "魯班種"]
    return group_name in percentage_groups

# Export to Excel
@app.route('/api/export_excel', methods=['GET'])
def export_excel():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM recipes")
    data = cur.fetchall()
    cur.close()
    conn.close()

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet("食譜")

    headers = ["食譜名稱", "分組", "食材", "重量 (g)", "百分比", "說明", "步驟", "建立時間", "上火溫度", "下火溫度", "烘烤時間", "旋風", "蒸汽"]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)

    row_num = 1
    for row in data:
        worksheet.write(row_num, 0, row['title'])
        worksheet.write(row_num, 1, row['group_name'])
        worksheet.write(row_num, 2, row['ingredient'])
        worksheet.write(row_num, 3, row['weight'])
        worksheet.write(row_num, 4, row['percent'])
        worksheet.write(row_num, 5, row['description'])
        worksheet.write(row_num, 6, row['steps'])
        worksheet.write(row_num, 7, row['timestamp'])
        worksheet.write(row_num, 8, row['top_heat'])
        worksheet.write(row_num, 9, row['bottom_heat'])
        worksheet.write(row_num, 10, row['bake_time'])
        worksheet.write(row_num, 11, '是' if row['convection'] else '否')
        worksheet.write(row_num, 12, '是' if row['steam'] else '否')
        row_num += 1

    workbook.close()
    output.seek(0)
    return send_file(output, attachment_filename="recipes.xlsx", as_attachment=True)

# Serve index.html
@app.route('/')
def index():
    html = '''  
  


  
  
    
      
         智能食材換算工具

        ×
      

      
        
          
            原始總麵粉量 (g)
            
          

          
            新總麵粉量 (g)
            
          

          
            換算比例
            
          

        

        
        
          ½ 倍

          ¾ 倍

          1 倍 (原始)

          1.5 倍

          2 倍

          2.5 倍

          3 倍

        

        
        
          
          同時調整非百分比分組的食材 (如內餡、裝飾等)
        

        
        
           計算換算結果
        
        
        
           換算結果

          

          
            
               複製結果
            
            
               應用到編輯表單
            
          

        

      

    

  


  
    
       TENG食譜管理系統 v3.1

      專業的烘焙食譜管理工具 - 支持分組食材、烘烤設定、自訂食材資料庫與智能換算

    


    
      食譜管理

      瀏覽食譜

      統計資訊

      設定

    


    
      
        新增 / 修改食譜


         只有需要計算百分比的分組才必須包含麵粉食材。麵團餡料A和B不需要麵粉但仍會計算百分比。


         食譜名稱

        
           食材分組管理
          
             新增分組
            
               智能換算工具
            
          

          

          
             新增食材
            含水率: 0%
          

        

         製作步驟

        
        
           烘烤設定
          
            上火溫度 (°C)

            下火溫度 (°C)

            烘烤時間 (min)

          

          
            旋風

            蒸汽

          

        

        
        
           儲存食譜
           清除表單
        

      

    


    
       
        食譜列表


        
           重新載入
           匯出 Excel
        

        
        
        
          食譜名稱:
          全部食譜


        

        
        
          
          建立時間 新→舊
建立時間 舊→新
名稱 A→Z
名稱 Z→A


        

        

      

    


    
       
        統計資訊


        
          0
食譜總數


          0
食材總數


          0
平均重量 (g)


          -
最新食譜


        

      

    

    
    
      
        自訂食材資料庫


         在此新增或修改食材的含水率(%)，會自動應用到食譜管理的計算中。


        
          
          
           新增/更新
        

        

      

    


    TENG食譜管理系統 v3.1 © 2023-2025 - 專業烘焙食譜管理工具

  


  儲存中，請稍候...


  
  
  
<script>
        let currentRecipeTitleForConversion = '';
        let originalTotalFlour = 0;
        let recipes = [];

        function showTab(tab) {
            document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
            document.getElementById(tab).classList.add('active');
            if (tab === 'recipeBrowse') loadRecipes();
            if (tab === 'stats') loadStats();
            if (tab === 'settings') loadIngredientsDB();
        }

        function addGroup() {
            const groupDiv = document.createElement('div');
            groupDiv.className = 'group';
            groupDiv.innerHTML = `
                <input type="text" class="group-name" placeholder="分組名稱">
                <div class="ingredients"></div>
                <button onclick="addIngredientToGroup(this.parentElement)">新增食材到此分組</button>
            `;
            document.getElementById('ingredientGroups').appendChild(groupDiv);
        }

        function addIngredient() {
            addIngredientToGroup(document.getElementById('ingredientGroups').lastChild || addGroup());
        }

        function addIngredientToGroup(group) {
            const ingDiv = document.createElement('div');
            ingDiv.className = 'ingredient';
            ingDiv.innerHTML = `
                <input type="text" class="ing-name" placeholder="食材" oninput="updateHydration(this)">
                <input type="number" class="ing-weight" placeholder="重量 (g)">
                <input type="text" class="ing-percent" placeholder="百分比">
                <input type="text" class="ing-desc" placeholder="說明">
                <button onclick="this.parentElement.remove()">刪除</button>
            `;
            group.querySelector('.ingredients').appendChild(ingDiv);
        }

        async function updateHydration(input) {
            const name = input.value.trim();
            if (name) {
                const db = await fetch('/api/ingredients_db').then(res => res.json());
                const ing = db.find(i => i.name === name);
                const hydration = ing ? ing.hydration : 0;
                document.getElementById('hydrationDisplay').textContent = `含水率: ${hydration}%`;
            }
        }

        function collectIngredients() {
            const ingredients = [];
            document.querySelectorAll('.group').forEach(group => {
                const groupName = group.querySelector('.group-name').value;
                group.querySelectorAll('.ingredient').forEach(ing => {
                    ingredients.push({
                        group: groupName,
                        name: ing.querySelector('.ing-name').value,
                        weight: parseFloat(ing.querySelector('.ing-weight').value) || 0,
                        percent: ing.querySelector('.ing-percent').value,
                        desc: ing.querySelector('.ing-desc').value
                    });
                });
            });
            return ingredients;
        }

        function saveOrUpdateRecipe() {
            const title = document.getElementById('recipeTitle').value;
            const ingredients = collectIngredients();
            const steps = document.getElementById('recipeSteps').value;
            const bakingInfo = {
                topHeat: parseInt(document.getElementById('topHeat').value),
                bottomHeat: parseInt(document.getElementById('bottomHeat').value),
                time: parseInt(document.getElementById('bakeTime').value),
                convection: document.getElementById('convection').checked,
                steam: document.getElementById('steam').checked
            };
            const editMode = document.getElementById('edit-mode').value === 'true';
            const oldTitle = document.getElementById('old-title').value;

            showLoading(true);
            const endpoint = editMode ? '/api/update_recipe' : '/api/save_recipe';
            const body = editMode ? {oldTitle, newTitle: title, ingredients, steps, bakingInfo} : {title, ingredients, steps, bakingInfo};

            fetch(endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            }).then(res => res.json()).then(data => {
                showLoading(false);
                alert(data.message || '儲存成功');
                clearForm();
            }).catch(err => {
                showLoading(false);
                alert('錯誤: ' + err);
            });
        }

        function clearForm() {
            document.getElementById('recipeTitle').value = '';
            document.getElementById('recipeSteps').value = '';
            document.getElementById('topHeat').value = 200;
            document.getElementById('bottomHeat').value = 200;
            document.getElementById('bakeTime').value = 30;
            document.getElementById('convection').checked = false;
            document.getElementById('steam').checked = false;
            document.getElementById('ingredientGroups').innerHTML = '';
            document.getElementById('edit-mode').value = 'false';
            document.getElementById('old-title').value = '';
        }

        function loadRecipes() {
            fetch('/api/recipes').then(res => res.json()).then(data => {
                recipes = data;
                populateFilter();
                displayRecipes();
                populateStats();
            });
        }

        function populateFilter() {
            const filter = document.getElementById('recipeFilter');
            filter.innerHTML = '<option>全部食譜</option>';
            recipes.forEach(r => {
                const option = document.createElement('option');
                option.value = r.title;
                option.textContent = r.title;
                filter.appendChild(option);
            });
        }

        function displayRecipes() {
            const filter = document.getElementById('recipeFilter').value;
            const sort = document.getElementById('sortOrder').value;
            let filtered = filter === '全部食譜' ? recipes : recipes.filter(r => r.title === filter);

            if (sort === 'timestamp_desc') filtered.sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp));
            if (sort === 'timestamp_asc') filtered.sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));
            if (sort === 'title_asc') filtered.sort((a,b) => a.title.localeCompare(b.title));
            if (sort === 'title_desc') filtered.sort((a,b) => b.title.localeCompare(a.title));

            const list = document.getElementById('recipeList');
            list.innerHTML = '';
            filtered.forEach(r => {
                const card = document.createElement('div');
                card.className = 'recipe-card';
                card.innerHTML = `
                    <h3>${r.title}</h3>
                    <p>建立時間: ${r.timestamp}</p>
                    <p>步驟: ${r.steps}</p>
                    <h4>烘烤設定</h4>
                    <p>上火: ${r.baking.topHeat}°C, 下火: ${r.baking.bottomHeat}°C, 時間: ${r.baking.time} min, 旋風: ${r.baking.convection ? '是' : '否'}, 蒸汽: ${r.baking.steam ? '是' : '否'}</p>
                    <h4>食材</h4>
                    <ul>${r.ingredients.map(i => `<li>${i.group}: ${i.name} - ${i.weight}g (${i.percent}) - ${i.desc}</li>`).join('')}</ul>
                    <button onclick="editRecipe('${r.title}')">編輯</button>
                    <button onclick="deleteRecipe('${r.title}')">刪除</button>
                `;
                list.appendChild(card);
            });
        }

        document.getElementById('recipeFilter').addEventListener('change', displayRecipes);
        document.getElementById('sortOrder').addEventListener('change', displayRecipes);

        function editRecipe(title) {
            const recipe = recipes.find(r => r.title === title);
            if (!recipe) return;

            document.getElementById('recipeTitle').value = recipe.title;
            document.getElementById('recipeSteps').value = recipe.steps;
            document.getElementById('topHeat').value = recipe.baking.topHeat;
            document.getElementById('bottomHeat').value = recipe.baking.bottomHeat;
            document.getElementById('bakeTime').value = recipe.baking.time;
            document.getElementById('convection').checked = recipe.baking.convection;
            document.getElementById('steam').checked = recipe.baking.steam;

            const groups = {};
            recipe.ingredients.forEach(i => {
                if (!groups[i.group]) groups[i.group] = [];
                groups[i.group].push(i);
            });

            const groupContainer = document.getElementById('ingredientGroups');
            groupContainer.innerHTML = '';
            Object.keys(groups).forEach(g => {
                addGroup();
                const groupDiv = groupContainer.lastChild;
                groupDiv.querySelector('.group-name').value = g;
                groups[g].forEach(ing => {
                    addIngredientToGroup(groupDiv);
                    const ingDiv = groupDiv.querySelector('.ingredients').lastChild;
                    ingDiv.querySelector('.ing-name').value = ing.name;
                    ingDiv.querySelector('.ing-weight').value = ing.weight;
                    ingDiv.querySelector('.ing-percent').value = ing.percent;
                    ingDiv.querySelector('.ing-desc').value = ing.desc;
                });
            });

            document.getElementById('edit-mode').value = 'true';
            document.getElementById('old-title').value = title;
            showTab('recipeManage');
        }

        function deleteRecipe(title) {
            if (confirm(`確認刪除 ${title}?`)) {
                fetch(`/api/delete_recipe?title=${title}`, {method: 'DELETE'}).then(res => res.json()).then(data => {
                    alert(data.message);
                    loadRecipes();
                });
            }
        }

        function loadStats() {
            if (recipes.length === 0) loadRecipes();
            const totalRecipes = recipes.length;
            let totalIngredients = 0;
            let totalWeight = 0;
            recipes.forEach(r => {
                totalIngredients += r.ingredients.length;
                r.ingredients.forEach(i => totalWeight += i.weight);
            });
            const avgWeight = totalRecipes > 0 ? (totalWeight / totalIngredients).toFixed(2) : 0;
            const latest = recipes.sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp))[0]?.title || '-';

            document.getElementById('totalRecipes').textContent = totalRecipes;
            document.getElementById('totalIngredients').textContent = totalIngredients;
            document.getElementById('avgWeight').textContent = avgWeight;
            document.getElementById('latestRecipe').textContent = latest;
        }

        function loadIngredientsDB() {
            fetch('/api/ingredients_db').then(res => res.json()).then(data => {
                const list = document.getElementById('ingredientsDBList');
                list.innerHTML = '';
                data.forEach(i => {
                    const item = document.createElement('div');
                    item.className = 'ing-db-item';
                    item.innerHTML = `${i.name} - ${i.hydration}% <button onclick="deleteIngredientDB('${i.name}')">刪除</button>`;
                    list.appendChild(item);
                });
            });
        }

        function saveIngredientDB() {
            const name = document.getElementById('ingName').value;
            const hydration = parseFloat(document.getElementById('ingHydration').value);
            if (!name) return alert('請輸入食材名稱');

            fetch('/api/save_ingredient_db', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, hydration})
            }).then(res => res.json()).then(data => {
                alert(data.message);
                loadIngredientsDB();
            });
        }

        function deleteIngredientDB(name) {
            if (confirm(`確認刪除 ${name}?`)) {
                fetch(`/api/delete_ingredient_db?name=${name}`, {method: 'DELETE'}).then(res => res.json()).then(data => {
                    alert(data.message);
                    loadIngredientsDB();
                });
            }
        }

        function openConversionModal() {
            const title = document.getElementById('recipeTitle').value;
            if (!title) return alert('請先輸入食譜名稱或選擇食譜');

            currentRecipeTitleForConversion = title;
            calculateOriginalFlour(title);
            document.getElementById('conversionModal').style.display = 'block';
        }

        function closeConversionModal() {
            document.getElementById('conversionModal').style.display = 'none';
        }

        function calculateOriginalFlour(title) {
            const recipe = recipes.find(r => r.title === title);
            if (!recipe) return;

            let totalFlour = 0;
            recipe.ingredients.forEach(ing => {
                if (isFlourIngredient(ing.name) && isPercentageGroup(ing.group)) {
                    totalFlour += ing.weight;
                }
            });
            originalTotalFlour = totalFlour;
            document.getElementById('original-flour').value = totalFlour;
            setRatio(1);
        }

        function setRatio(ratio) {
            const newFlour = originalTotalFlour * ratio;
            document.getElementById('new-flour').value = newFlour;
            document.getElementById('conversion-ratio').value = ratio.toFixed(2);
        }

        function calculateConversion() {
            const newTotalFlour = parseFloat(document.getElementById('new-flour').value);
            const includeNonPercentage = document.getElementById('include-non-percentage').checked;

            fetch('/api/calculate_conversion', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    recipeTitle: currentRecipeTitleForConversion,
                    newTotalFlour,
                    includeNonPercentageGroups: includeNonPercentage
                })
            }).then(res => res.json()).then(data => {
                if (data.status === 'error') return alert(data.message);

                const resultDiv = document.getElementById('converted-ingredients');
                resultDiv.innerHTML = '<ul>' + data.ingredients.map(i => `<li>${i.group}: ${i.name} - ${i.weight}g (${i.percent}) - ${i.desc}</li>`).join('') + '</ul>';
            });
        }

        function copyConversionResult() {
            const result = document.getElementById('converted-ingredients').innerText;
            navigator.clipboard.writeText(result).then(() => alert('已複製'));
        }

        function applyToEditForm() {
            // Implement application to form
            // For now, alert as placeholder
            alert('應用功能待實現');
        }

        function isFlourIngredient(name) {
            const keywords = ["高筋麵粉", "中筋麵粉", "低筋麵粉", "全麥麵粉", "裸麥粉", "麵粉"];
            return keywords.some(k => name.includes(k));
        }

        function isPercentageGroup(group) {
            const groups = ["主麵團", "麵團餡料A", "麵團餡料B", "波蘭種", "液種", "中種", "魯班種"];
            return groups.includes(group);
        }

        function showLoading(show) {
            document.getElementById('loading').style.display = show ? 'block' : 'none';
        }

        // Initial load
        loadRecipes();
    </script>
<style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        header, footer { text-align: center; }
        nav { margin-bottom: 20px; }
        nav button { margin-right: 10px; }
        .tab-content { display: none; margin-bottom: 20px; }
        .tab-content.active { display: block; }
        .modal { display: none; position: fixed; z-index: 1; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.4); }
        .modal-content { background-color: #fefefe; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 80%; }
        .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; }
        .close:hover, .close:focus { color: black; text-decoration: none; cursor: pointer; }
        #ingredientGroups { margin-top: 10px; }
        .group { border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
        .ingredient { margin-bottom: 5px; }
        #recipeList { margin-top: 10px; }
        .recipe-card { border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; }
        #loading { display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(255,255,255,0.8); padding: 20px; border: 1px solid #ccc; }
        #ingredientsDBList { margin-top: 10px; }
        .ing-db-item { margin-bottom: 5px; }
    </style>'''
    return render_template_string(html)

if __name__ == '__main__':
    app.run(debug=True)
