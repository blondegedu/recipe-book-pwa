#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import re
from datetime import datetime
import os

RECIPES_FILE = 'recipes.json'

def extract_recipe(url):
    """Extract recipe from URL using JSON-LD schema with HTML fallback"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
    
    title = 'Untitled Recipe'
    ingredients = []
    instructions = []
    
    # Try JSON-LD first
    for match in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(match.group(1))
            
            # Handle @graph structure
            if isinstance(data, dict) and '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'Recipe':
                        data = item
                        break
            
            # Handle list structure
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Recipe':
                        data = item
                        break
            
            # Check if we found a Recipe
            if data.get('@type') == 'Recipe':
                title = data.get('name', title)
                
                # Get ingredients
                if data.get('recipeIngredient'):
                    ingredients = data.get('recipeIngredient', [])
                
                # Get instructions
                if data.get('recipeInstructions'):
                    inst_data = data.get('recipeInstructions', [])
                    for s in inst_data:
                        if isinstance(s, dict):
                            instructions.append(s.get('text', ''))
                        elif isinstance(s, str):
                            instructions.append(s)
                
                # If we got both, we're done
                if ingredients and instructions:
                    return {
                        'title': title,
                        'ingredients': ingredients,
                        'instructions': instructions,
                        'url': url,
                        'date': datetime.now().isoformat(),
                        'category': 'Uncategorized'
                    }
        except:
            continue
    
    # HTML Fallback - look for common patterns
    if not ingredients:
        # Try to find ingredient lists - look for ul/ol within ingredient sections
        ing_section = re.search(r'<(?:article|div)[^>]*class="[^"]*ingredient[^"]*"[^>]*>(.*?)</(?:article|div)>', html, re.IGNORECASE | re.DOTALL)
        if ing_section:
            matches = re.findall(r'<li[^>]*>(.*?)</li>', ing_section.group(1), re.IGNORECASE | re.DOTALL)
            if matches:
                ingredients = [re.sub(r'<[^>]+>', '', m).strip() for m in matches if m.strip()]
    
    if not instructions:
        # Try to find instruction lists - look for ol/ul within direction/instruction sections
        inst_section = re.search(r'<div[^>]*class="[^"]*(?:direction|instruction|step)[^"]*"[^>]*>(.*?)</ol>', html, re.IGNORECASE | re.DOTALL)
        if inst_section:
            matches = re.findall(r'<li[^>]*>(.*?)</li>', inst_section.group(1), re.IGNORECASE | re.DOTALL)
            if matches:
                instructions = [re.sub(r'<[^>]+>', '', m).strip() for m in matches if m.strip()]
    
    # If we got something, return it
    if title != 'Untitled Recipe' or ingredients or instructions:
        return {
            'title': title,
            'ingredients': ingredients if ingredients else ['No ingredients found'],
            'instructions': instructions if instructions else ['No instructions found'],
            'url': url,
            'date': datetime.now().isoformat(),
            'category': 'Uncategorized'
        }
    
    raise Exception('No recipe found')

def load_recipes():
    if os.path.exists(RECIPES_FILE):
        with open(RECIPES_FILE, 'r') as f:
            return json.load(f)
    return []

def save_recipes(recipes):
    with open(RECIPES_FILE, 'w') as f:
        json.dump(recipes, f, indent=2)

class RecipeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/add-manual':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(MANUAL_FORM_HTML.encode())
        elif self.path.startswith('/edit/'):
            recipe_index = int(self.path.split('/')[-1])
            recipes = load_recipes()
            if 0 <= recipe_index < len(recipes):
                recipe = recipes[recipe_index]
                edit_html = EDIT_FORM_HTML.replace('{{RECIPE_INDEX}}', str(recipe_index))
                edit_html = edit_html.replace('{{TITLE}}', recipe['title'])
                edit_html = edit_html.replace('{{CATEGORY}}', recipe['category'])
                edit_html = edit_html.replace('{{INGREDIENTS}}', '\\n'.join(recipe['ingredients']))
                edit_html = edit_html.replace('{{INSTRUCTIONS}}', '\\n'.join(recipe['instructions']))
                edit_html = edit_html.replace('{{NOTES}}', recipe.get('notes', ''))
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(edit_html.encode())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == '/recipes':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(load_recipes()).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/add':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            url = data.get('url', '')
            
            try:
                recipe = extract_recipe(url)
                recipes = load_recipes()
                recipes.append(recipe)
                save_recipes(recipes)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(recipe).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/add-manual-submit':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            
            recipe = {
                'title': data.get('title', 'Untitled Recipe'),
                'category': data.get('category', 'Other'),
                'ingredients': [i.strip() for i in data.get('ingredients', '').split('\n') if i.strip()],
                'instructions': [i.strip() for i in data.get('instructions', '').split('\n') if i.strip()],
                'notes': data.get('notes', ''),
                'url': '',
                'date': datetime.now().isoformat()
            }
            
            recipes = load_recipes()
            recipes.append(recipe)
            save_recipes(recipes)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif self.path == '/set-notes':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            notes = data.get('notes', '')
            
            recipes = load_recipes()
            if 0 <= index < len(recipes):
                recipes[index]['notes'] = notes
                save_recipes(recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif self.path == '/rename':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            title = data.get('title', '')
            
            recipes = load_recipes()
            if 0 <= index < len(recipes):
                recipes[index]['title'] = title
                save_recipes(recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif self.path == '/set-category':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            category = data.get('category', '')
            
            recipes = load_recipes()
            if 0 <= index < len(recipes):
                recipes[index]['category'] = category
                save_recipes(recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif self.path == '/delete':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            
            recipes = load_recipes()
            if 0 <= index < len(recipes):
                recipes.pop(index)
                save_recipes(recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif self.path == '/edit-submit':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            
            recipes = load_recipes()
            if 0 <= index < len(recipes):
                recipes[index]['title'] = data.get('title', '')
                recipes[index]['category'] = data.get('category', 'Other')
                recipes[index]['ingredients'] = [i.strip() for i in data.get('ingredients', '').split('\\n') if i.strip()]
                recipes[index]['instructions'] = [i.strip() for i in data.get('instructions', '').split('\\n') if i.strip()]
                recipes[index]['notes'] = data.get('notes', '')
                save_recipes(recipes)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            else:
                self.send_response(400)
                self.end_headers()
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

MANUAL_FORM_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Add Recipe Manually - Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; padding: 20px; overflow-x: hidden; }
        .container { max-width: 800px; margin: 0 auto; width: 100%; }
        h1 { color: #2d5016; margin-bottom: 20px; cursor: pointer; word-wrap: break-word; }
        .form-container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); max-width: 100%; }
        label { display: block; color: #2d5016; font-weight: bold; margin-top: 20px; margin-bottom: 5px; }
        input, select, textarea { width: 100%; max-width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; font-family: Georgia, serif; box-sizing: border-box; }
        textarea { min-height: 150px; resize: vertical; }
        button { padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .help-text { font-size: 14px; color: #666; margin-top: 5px; }
        .status { padding: 15px; border-radius: 4px; margin-top: 20px; }
        .status.success { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .form-container { padding: 15px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 onclick="window.location.href='/'" title="Back to main page">🍳 Recipe Book - Add Manually</h1>
        
        <div class="form-container">
            <div style="margin-bottom: 20px; padding: 15px; background: #fff9e6; border-radius: 4px; border: 2px dashed #f4d03f;">
                <strong style="color: #2d5016;">Quick Paste:</strong> Have a recipe copied? 
                <button type="button" onclick="showQuickPaste()" style="padding: 8px 16px; margin-left: 10px;">Paste & Auto-Fill</button>
            </div>
            
            <div id="quickPasteModal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000;">
                <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 30px; border-radius: 8px; max-width: 600px; width: 90%;">
                    <h2 style="color: #2d5016; margin-bottom: 15px;">Paste Your Recipe</h2>
                    <textarea id="quickPasteText" placeholder="Paste the entire recipe here..." style="width: 100%; min-height: 300px; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-family: Georgia, serif;"></textarea>
                    <div style="margin-top: 15px;">
                        <button type="button" onclick="parseRecipe()" style="padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">Parse Recipe</button>
                        <button type="button" onclick="closeQuickPaste()" style="padding: 12px 24px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px;">Cancel</button>
                    </div>
                </div>
            </div>
            
            <form id="manualForm">
                <label for="title">Recipe Title *</label>
                <input type="text" id="title" required placeholder="e.g., Chocolate Chip Cookies">
                
                <label for="category">Category</label>
                <select id="category">
                    <option value="Other">Other</option>
                    <option value="Breakfast">Breakfast</option>
                    <option value="Lunch">Lunch</option>
                    <option value="Dinner">Dinner</option>
                    <option value="Snack">Snack</option>
                    <option value="Dessert">Dessert</option>
                    <option value="Condiment">Condiment</option>
                </select>
                
                <label for="ingredients">Ingredients *</label>
                <textarea id="ingredients" required placeholder="Enter one ingredient per line:
1 cup flour
2 eggs
1/2 cup sugar"></textarea>
                <div class="help-text">One ingredient per line</div>
                
                <label for="instructions">Instructions *</label>
                <textarea id="instructions" required placeholder="Enter one step per line:
Preheat oven to 350°F
Mix dry ingredients
Add wet ingredients
Bake for 20 minutes"></textarea>
                <div class="help-text">One instruction per line</div>
                
                <label for="notes">Notes (optional)</label>
                <textarea id="notes" style="min-height: 80px;" placeholder="Any additional notes..."></textarea>
                
                <button type="submit">Add Recipe</button>
                <button type="button" onclick="window.location.href='/'" style="background: #6c757d; margin-left: 10px;">Cancel</button>
            </form>
            
            <div id="status"></div>
        </div>
    </div>

    <script>
        document.getElementById('manualForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const btn = e.target.querySelector('button[type="submit"]');
            const status = document.getElementById('status');
            
            btn.disabled = true;
            btn.textContent = 'Adding...';
            status.innerHTML = '';
            
            const data = {
                title: document.getElementById('title').value,
                category: document.getElementById('category').value,
                ingredients: document.getElementById('ingredients').value,
                instructions: document.getElementById('instructions').value,
                notes: document.getElementById('notes').value
            };
            
            try {
                const res = await fetch('/add-manual-submit', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                
                if (res.ok) {
                    status.innerHTML = '<div class="status success">✅ Recipe added! Redirecting...</div>';
                    setTimeout(() => window.location.href = '/', 1500);
                } else {
                    status.innerHTML = '<div class="status error">❌ Error adding recipe</div>';
                    btn.disabled = false;
                    btn.textContent = 'Add Recipe';
                }
            } catch (e) {
                status.innerHTML = '<div class="status error">❌ Error: ' + e.message + '</div>';
                btn.disabled = false;
                btn.textContent = 'Add Recipe';
            }
        });
        
        function showQuickPaste() {
            document.getElementById('quickPasteModal').style.display = 'block';
        }
        
        function closeQuickPaste() {
            document.getElementById('quickPasteModal').style.display = 'none';
        }
        
        function parseRecipe() {
            const text = document.getElementById('quickPasteText').value;
            if (!text.trim()) return;
            
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
            
            // Extract title (first non-empty line)
            const title = lines[0] || 'Untitled Recipe';
            document.getElementById('title').value = title;
            
            // Find ingredients section
            let ingredientsStart = -1;
            let ingredientsEnd = -1;
            let instructionsStart = -1;
            
            for (let i = 0; i < lines.length; i++) {
                const lower = lines[i].toLowerCase();
                if (lower.includes('ingredient') && ingredientsStart === -1) {
                    ingredientsStart = i + 1;
                } else if ((lower.includes('instruction') || lower.includes('direction') || lower.includes('step')) && instructionsStart === -1) {
                    if (ingredientsStart !== -1 && ingredientsEnd === -1) {
                        ingredientsEnd = i;
                    }
                    instructionsStart = i + 1;
                }
            }
            
            // Extract ingredients
            if (ingredientsStart !== -1) {
                const endIdx = ingredientsEnd !== -1 ? ingredientsEnd : (instructionsStart !== -1 ? instructionsStart - 1 : lines.length);
                const ingredients = lines.slice(ingredientsStart, endIdx)
                    .filter(l => !l.toLowerCase().includes('ingredient'))
                    .join('\\n');
                document.getElementById('ingredients').value = ingredients;
            }
            
            // Extract instructions
            if (instructionsStart !== -1) {
                const instructions = lines.slice(instructionsStart)
                    .filter(l => !l.toLowerCase().includes('instruction') && !l.toLowerCase().includes('direction'))
                    .join('\\n');
                document.getElementById('instructions').value = instructions;
            }
            
            closeQuickPaste();
        }
    </script>
</body>
</html>'''

EDIT_FORM_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Recipe - Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; padding: 20px; overflow-x: hidden; }
        .container { max-width: 800px; margin: 0 auto; width: 100%; }
        h1 { color: #2d5016; margin-bottom: 20px; cursor: pointer; word-wrap: break-word; }
        .form-container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); max-width: 100%; }
        label { display: block; color: #2d5016; font-weight: bold; margin-top: 20px; margin-bottom: 5px; }
        input, select, textarea { width: 100%; max-width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; font-family: Georgia, serif; box-sizing: border-box; }
        textarea { min-height: 150px; resize: vertical; }
        button { padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .btn-cancel { background: #6c757d; color: white; margin-left: 10px; }
        .btn-cancel:hover { background: #5a6268; }
        .status { padding: 15px; border-radius: 4px; margin-top: 20px; }
        .status.success { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .form-container { padding: 15px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 onclick="window.location.href='/'" title="Back to main page">🍳 Recipe Book - Edit Recipe</h1>
        
        <div class="form-container">
            <form id="editForm">
                <input type="hidden" id="recipeIndex" value="{{RECIPE_INDEX}}">
                
                <label for="title">Recipe Title *</label>
                <input type="text" id="title" required value="{{TITLE}}">
                
                <label for="category">Category *</label>
                <select id="category" required>
                    <option value="Breakfast">Breakfast</option>
                    <option value="Lunch">Lunch</option>
                    <option value="Dinner">Dinner</option>
                    <option value="Snack">Snack</option>
                    <option value="Dessert">Dessert</option>
                    <option value="Condiment">Condiment</option>
                    <option value="Other">Other</option>
                </select>
                
                <label for="ingredients">Ingredients * (one per line)</label>
                <textarea id="ingredients" required placeholder="1 cup flour&#10;2 eggs&#10;1/2 cup sugar">{{INGREDIENTS}}</textarea>
                
                <label for="instructions">Instructions * (one per line)</label>
                <textarea id="instructions" required placeholder="Preheat oven to 350°F&#10;Mix dry ingredients&#10;Add wet ingredients">{{INSTRUCTIONS}}</textarea>
                
                <label for="notes">Notes (optional)</label>
                <textarea id="notes" style="min-height: 100px;">{{NOTES}}</textarea>
                
                <button type="submit" id="saveBtn">Save Changes</button>
                <button type="button" class="btn-cancel" onclick="window.location.href='/'">Cancel</button>
                
                <div id="status"></div>
            </form>
        </div>
    </div>
    
    <script>
        document.getElementById('category').value = '{{CATEGORY}}';
        
        document.getElementById('editForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('saveBtn');
            const status = document.getElementById('status');
            
            btn.disabled = true;
            btn.textContent = 'Saving...';
            status.innerHTML = '';
            
            try {
                const response = await fetch('/edit-submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        index: parseInt(document.getElementById('recipeIndex').value),
                        title: document.getElementById('title').value,
                        category: document.getElementById('category').value,
                        ingredients: document.getElementById('ingredients').value,
                        instructions: document.getElementById('instructions').value,
                        notes: document.getElementById('notes').value
                    })
                });
                
                if (response.ok) {
                    status.innerHTML = '<div class="status success">✅ Recipe updated! Redirecting...</div>';
                    setTimeout(() => window.location.href = '/', 1000);
                } else {
                    status.innerHTML = '<div class="status error">❌ Failed to update recipe</div>';
                    btn.disabled = false;
                    btn.textContent = 'Save Changes';
                }
            } catch (e) {
                status.innerHTML = '<div class="status error">❌ Error: ' + e.message + '</div>';
                btn.disabled = false;
                btn.textContent = 'Save Changes';
            }
        });
    </script>
</body>
</html>'''

HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; padding: 20px; overflow-x: hidden; }
        .container { max-width: 1200px; margin: 0 auto; width: 100%; }
        h1 { color: #2d5016; margin-bottom: 20px; word-wrap: break-word; }
        .recipe-list { display: grid; gap: 20px; margin-top: 20px; }
        .recipe-card { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; cursor: pointer; max-width: 100%; }
        .recipe-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .recipe-card h2 { color: #2d5016; font-size: 22px; margin-bottom: 10px; word-wrap: break-word; }
        .recipe-full { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; margin-bottom: 20px; max-width: 100%; overflow-wrap: break-word; }
        .recipe-full h2 { color: #2d5016; font-size: 28px; margin-bottom: 20px; word-wrap: break-word; }
        .ingredients, .instructions { margin: 20px 0; }
        .ingredients h3, .instructions h3 { color: #2d5016; margin-bottom: 15px; }
        .ingredients li { padding: 8px 0; word-wrap: break-word; }
        .instructions li { padding: 10px 0; margin-bottom: 10px; word-wrap: break-word; }
        button { padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin: 10px 10px 10px 0; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-danger:hover { background: #c82333; }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .recipe-full { padding: 15px; }
            button { padding: 10px 16px; font-size: 14px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 onclick="backToList()" style="cursor: pointer;">🍳 Recipe Book</h1>
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <input type="text" id="urlInput" placeholder="Paste recipe URL..." style="width: 70%; max-width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; box-sizing: border-box;" />
            <button onclick="addRecipe()" id="addBtn">Add Recipe</button>
            <div id="status" style="margin-top: 10px;"></div>
            <p style="margin-top: 10px; font-size: 14px; color: #666; word-wrap: break-word;">
                If a URL doesn't work, try <a href="https://www.justtherecipe.com/" target="_blank" style="color: #8b4513;">JustTheRecipe.com</a> or <a href="https://video2recipe.com/" target="_blank" style="color: #8b4513;">Video2Recipe.com</a> first, then paste the result URL here.<br>
                Or <a href="/add-manual" style="color: #2d5016; font-weight: bold;">add a recipe manually</a>.
            </p>
        </div>
        <div style="display: flex; gap: 10px; margin-bottom: 20px;">
            <input type="text" id="searchBox" placeholder="Search recipes..." onkeyup="filterRecipes()" style="flex: 1; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; min-width: 0; box-sizing: border-box;" />
            <select id="sortBox" onchange="filterRecipes()" style="padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; background: white; box-sizing: border-box;">
                <option value="date-newest">Newest First</option>
                <option value="date-oldest">Oldest First</option>
                <option value="alphabetical">A-Z</option>
                <option value="category">By Category</option>
            </select>
        </div>
        <div id="recipes"></div>
    </div>

    <script>
        let recipes = [];
        let viewingRecipe = null;

        async function addRecipe() {
            const input = document.getElementById('urlInput');
            const btn = document.getElementById('addBtn');
            const status = document.getElementById('status');
            const url = input.value.trim();
            
            if (!url) return;
            
            btn.disabled = true;
            btn.textContent = 'Adding...';
            status.innerHTML = '';
            
            try {
                const res = await fetch('/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                
                if (res.ok) {
                    status.innerHTML = '<div style="color: green;">✅ Recipe added!</div>';
                    input.value = '';
                    await loadRecipes();
                    setTimeout(() => status.innerHTML = '', 3000);
                } else {
                    const error = await res.json();
                    status.innerHTML = '<div style="color: red;">❌ Error: ' + error.error + '</div>';
                }
            } catch (e) {
                status.innerHTML = '<div style="color: red;">❌ Error: ' + e.message + '</div>';
            }
            
            btn.disabled = false;
            btn.textContent = 'Add Recipe';
        }

        async function loadRecipes() {
            const res = await fetch('/recipes');
            recipes = await res.json();
            displayRecipes();
        }

        function displayRecipes() {
            const container = document.getElementById('recipes');
            
            if (viewingRecipe !== null) {
                showRecipe(viewingRecipe);
                return;
            }
            
            const search = document.getElementById('searchBox').value.toLowerCase();
            const sortBy = document.getElementById('sortBox').value;
            let filtered = recipes;
            
            if (search) {
                filtered = recipes.filter(r => 
                    r.title.toLowerCase().includes(search) ||
                    (r.ingredients || []).join(' ').toLowerCase().includes(search) ||
                    (r.instructions || []).join(' ').toLowerCase().includes(search) ||
                    (r.category || '').toLowerCase().includes(search)
                );
            }
            
            // Sort
            filtered = [...filtered]; // Make a copy to avoid mutating original
            if (sortBy === 'date-newest') {
                filtered.sort((a, b) => new Date(b.date) - new Date(a.date));
            } else if (sortBy === 'date-oldest') {
                filtered.sort((a, b) => new Date(a.date) - new Date(b.date));
            } else if (sortBy === 'alphabetical') {
                filtered.sort((a, b) => a.title.localeCompare(b.title));
            } else if (sortBy === 'category') {
                const categoryOrder = ['Breakfast', 'Lunch', 'Dinner', 'Snack', 'Dessert', 'Condiment', 'Other'];
                filtered.sort((a, b) => {
                    const catA = a.category || 'Other';
                    const catB = b.category || 'Other';
                    const orderA = categoryOrder.indexOf(catA);
                    const orderB = categoryOrder.indexOf(catB);
                    const indexA = orderA === -1 ? 999 : orderA;
                    const indexB = orderB === -1 ? 999 : orderB;
                    return indexA - indexB || a.title.localeCompare(b.title);
                });
            }
            
            if (filtered.length === 0) {
                container.innerHTML = '<p>No recipes found.</p>';
                return;
            }
            
            container.innerHTML = '<div class="recipe-list">' + filtered.map((recipe) => {
                const index = recipes.indexOf(recipe);
                const date = new Date(recipe.date).toLocaleDateString();
                return `
                    <div class="recipe-card" onclick="viewRecipe(${index})">
                        <h2>${recipe.title}</h2>
                        <p>${recipe.category || 'Uncategorized'} • Added ${date}</p>
                    </div>
                `;
            }).join('') + '</div>';
        }

        function filterRecipes() {
            viewingRecipe = null;
            displayRecipes();
        }

        function viewRecipe(index) {
            viewingRecipe = index;
            showRecipe(index);
        }

        function showRecipe(index) {
            const recipe = recipes[index];
            const container = document.getElementById('recipes');
            
            const ingredients = (recipe.ingredients || []).length 
                ? '<ul>' + recipe.ingredients.map(i => `<li>${i}</li>`).join('') + '</ul>'
                : '<p>No ingredients</p>';
            
            const instructions = (recipe.instructions || []).length
                ? '<ol>' + recipe.instructions.map(i => `<li>${i}</li>`).join('') + '</ol>'
                : '<p>No instructions</p>';
            
            container.innerHTML = `
                <div class="recipe-full">
                    <h2 onclick="editTitle(${index})" style="cursor: pointer;" title="Click to rename">${recipe.title}</h2>
                    <div style="margin: 20px 0;">
                        <label><strong>Category:</strong></label>
                        <select id="category-input-${index}" onchange="saveCategory(${index})" style="padding: 8px; border: 2px solid #d4c5b9; border-radius: 4px; margin-left: 10px; width: 200px;">
                            <option value="">Select category...</option>
                            <option value="Breakfast" ${recipe.category === 'Breakfast' ? 'selected' : ''}>Breakfast</option>
                            <option value="Lunch" ${recipe.category === 'Lunch' ? 'selected' : ''}>Lunch</option>
                            <option value="Dinner" ${recipe.category === 'Dinner' ? 'selected' : ''}>Dinner</option>
                            <option value="Snack" ${recipe.category === 'Snack' ? 'selected' : ''}>Snack</option>
                            <option value="Dessert" ${recipe.category === 'Dessert' ? 'selected' : ''}>Dessert</option>
                            <option value="Condiment" ${recipe.category === 'Condiment' ? 'selected' : ''}>Condiment</option>
                            <option value="Other" ${recipe.category === 'Other' ? 'selected' : ''}>Other</option>
                        </select>
                    </div>
                    <div class="ingredients">
                        <h3>Ingredients</h3>
                        ${ingredients}
                    </div>
                    <div class="instructions">
                        <h3>Instructions</h3>
                        ${instructions}
                    </div>
                    <div style="margin: 20px 0;">
                        <label><strong>Notes:</strong></label><br/>
                        <textarea id="notes-input-${index}" 
                                  placeholder="Add your notes here..." 
                                  style="width: 100%; min-height: 100px; padding: 10px; border: 2px solid #d4c5b9; border-radius: 4px; margin-top: 10px; font-family: Georgia, serif; font-size: 14px;">${recipe.notes || ''}</textarea>
                        <button onclick="saveNotes(${index})" style="padding: 8px 16px; margin-top: 10px;">Save Notes</button>
                    </div>
                    <button onclick="backToList()">← Back to Recipes</button>
                    <button onclick="window.location.href='/edit/${index}'">Edit Recipe</button>
                    <button class="btn-danger" onclick="deleteRecipe(${index})">Delete Recipe</button>
                </div>
            `;
        }

        function backToList() {
            viewingRecipe = null;
            displayRecipes();
        }

        async function saveCategory(index) {
            const select = document.getElementById(`category-input-${index}`);
            const category = select.value;
            
            await fetch('/set-category', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({index, category})
            });
            
            await loadRecipes();
        }

        async function saveNotes(index) {
            const textarea = document.getElementById(`notes-input-${index}`);
            const notes = textarea.value;
            
            await fetch('/set-notes', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({index, notes})
            });
            
            await loadRecipes();
        }

        function editTitle(index) {
            const currentTitle = recipes[index].title;
            const newTitle = prompt('Enter new recipe title:', currentTitle);
            
            if (newTitle && newTitle.trim() && newTitle !== currentTitle) {
                renameRecipe(index, newTitle.trim());
            }
        }

        async function renameRecipe(index, title) {
            await fetch('/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({index, title})
            });
            
            await loadRecipes();
        }

        async function deleteRecipe(index) {
            if (!confirm('Delete this recipe?')) return;
            
            await fetch('/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({index})
            });
            
            viewingRecipe = null;
            await loadRecipes();
        }

        loadRecipes();
    </script>
</body>
</html>'''

if __name__ == '__main__':
    port = 8080
    server = HTTPServer(('0.0.0.0', port), RecipeHandler)
    print(f'✅ Recipe Book Server Running on port {port} Test Printing!')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 Server stopped')
