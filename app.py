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
    with open('index.html', 'r', encoding='utf-8') as f:
        html = f.read()
    return html

if __name__ == '__main__':
    app.run(debug=True)
