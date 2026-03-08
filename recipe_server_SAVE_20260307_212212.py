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
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #2d5016; margin-bottom: 20px; }
        .recipe-list { display: grid; gap: 20px; margin-top: 20px; }
        .recipe-card { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; cursor: pointer; }
        .recipe-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .recipe-card h2 { color: #2d5016; font-size: 22px; margin-bottom: 10px; }
        .recipe-full { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; margin-bottom: 20px; }
        .recipe-full h2 { color: #2d5016; font-size: 28px; margin-bottom: 20px; }
        .ingredients, .instructions { margin: 20px 0; }
        .ingredients h3, .instructions h3 { color: #2d5016; margin-bottom: 15px; }
        .ingredients li { padding: 8px 0; }
        .instructions li { padding: 10px 0; margin-bottom: 10px; }
        button { padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin: 10px 10px 10px 0; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-danger:hover { background: #c82333; }
    </style>
</head>
<body>
    <div class="container">
        <h1 onclick="backToList()" style="cursor: pointer;">🍳 Recipe Book</h1>
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <input type="text" id="urlInput" placeholder="Paste recipe URL..." style="width: 70%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px;" />
            <button onclick="addRecipe()" id="addBtn">Add Recipe</button>
            <div id="status" style="margin-top: 10px;"></div>
            <p style="margin-top: 10px; font-size: 14px; color: #666;">
                If a URL doesn't work, try <a href="https://www.justtherecipe.com/" target="_blank" style="color: #8b4513;">JustTheRecipe.com</a> or <a href="https://video2recipe.com/" target="_blank" style="color: #8b4513;">Video2Recipe.com</a> first, then paste the result URL here.
            </p>
        </div>
        <div style="display: flex; gap: 10px; margin-bottom: 20px;">
            <input type="text" id="searchBox" placeholder="Search recipes..." onkeyup="filterRecipes()" style="flex: 1; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px;" />
            <select id="sortBox" onchange="filterRecipes()" style="padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; background: white;">
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
    print(f'✅ Recipe Book Server Running on port {port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 Server stopped')
