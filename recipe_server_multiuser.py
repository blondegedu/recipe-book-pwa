#!/usr/bin/env python3
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
import hashlib
import secrets
import re
from bs4 import BeautifulSoup
import requests

# File paths
USERS_FILE = 'users.json'
SESSIONS_FILE = 'sessions.json'
RECIPES_DIR = 'user_recipes'

# Ensure directories exist
os.makedirs(RECIPES_DIR, exist_ok=True)

# Session duration: 90 days
SESSION_DURATION = timedelta(days=90)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)

def load_recipes(user_id):
    recipe_file = os.path.join(RECIPES_DIR, f'{user_id}.json')
    if os.path.exists(recipe_file):
        with open(recipe_file, 'r') as f:
            return json.load(f)
    return []

def save_recipes(user_id, recipes):
    recipe_file = os.path.join(RECIPES_DIR, f'{user_id}.json')
    with open(recipe_file, 'w') as f:
        json.dump(recipes, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(user_id):
    sessions = load_sessions()
    session_token = secrets.token_urlsafe(32)
    expiry = (datetime.now() + SESSION_DURATION).isoformat()
    sessions[session_token] = {
        'user_id': user_id,
        'expiry': expiry
    }
    save_sessions(sessions)
    return session_token

def validate_session(session_token):
    if not session_token:
        return None
    sessions = load_sessions()
    session = sessions.get(session_token)
    if not session:
        return None
    expiry = datetime.fromisoformat(session['expiry'])
    if datetime.now() > expiry:
        del sessions[session_token]
        save_sessions(sessions)
        return None
    return session['user_id']

def extract_recipe(url):
    """Extract recipe from URL using JSON-LD schema or HTML parsing"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try JSON-LD first
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                
                # Handle @graph structure
                if isinstance(data, dict) and '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                if isinstance(data, dict) and data.get('@type') == 'Recipe':
                    ingredients = data.get('recipeIngredient', [])
                    if isinstance(ingredients, str):
                        ingredients = [ingredients]
                    
                    instructions = []
                    inst_data = data.get('recipeInstructions', [])
                    if isinstance(inst_data, str):
                        instructions = [inst_data]
                    elif isinstance(inst_data, list):
                        for inst in inst_data:
                            if isinstance(inst, str):
                                instructions.append(inst)
                            elif isinstance(inst, dict):
                                instructions.append(inst.get('text', ''))
                    
                    return {
                        'title': data.get('name', 'Untitled Recipe'),
                        'ingredients': ingredients,
                        'instructions': instructions
                    }
            except:
                continue
        
        # Fallback to HTML parsing - be more selective
        # Try title tag first, then h1
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text().strip()
            # Clean up common title patterns
            title_text = title_text.split('|')[0].strip()  # Remove "| Site Name"
            title_text = title_text.split('-')[0].strip()  # Remove "- Site Name"
        else:
            h1 = soup.find('h1')
            title_text = h1.get_text().strip() if h1 else 'Untitled Recipe'
        
        ingredients = []
        # Look for ingredient lists specifically
        for tag in soup.find_all('li'):
            text = tag.get_text().strip()
            # Must have measurement words and be reasonable length
            if (any(word in text.lower() for word in ['cup', 'tablespoon', 'teaspoon', 'tbsp', 'tsp', 'oz', 'lb', 'gram', 'kg', 'ml', 'liter']) 
                and len(text) < 200 and len(text) > 5):
                ingredients.append(text)
                if len(ingredients) >= 30:  # Limit to 30 ingredients
                    break
        
        instructions = []
        # Look for instruction steps
        for tag in soup.find_all(['li', 'p']):
            text = tag.get_text().strip()
            # Must have cooking verbs and be reasonable length
            if (any(word in text.lower() for word in ['heat', 'cook', 'bake', 'mix', 'add', 'stir', 'place', 'combine', 'whisk', 'pour'])
                and len(text) > 20 and len(text) < 500):
                instructions.append(text)
                if len(instructions) >= 20:  # Limit to 20 steps
                    break
        
        return {
            'title': title_text,
            'ingredients': ingredients,
            'instructions': instructions
        }
    except Exception as e:
        raise Exception(f"Failed to extract recipe: {str(e)}")

LOGIN_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
        .container { max-width: 400px; width: 100%; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { color: #2d5016; margin-bottom: 30px; text-align: center; }
        label { display: block; color: #2d5016; font-weight: bold; margin-top: 15px; margin-bottom: 5px; }
        input { width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; font-family: Georgia, serif; }
        button { width: 100%; padding: 14px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .error { color: #721c24; background: #f8d7da; padding: 12px; border-radius: 4px; margin-top: 15px; }
        .link { text-align: center; margin-top: 20px; color: #666; }
        .link a { color: #2d5016; font-weight: bold; text-decoration: none; }
        .link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍳 Recipe Book</h1>
        <form id="loginForm">
            <label for="email">Email</label>
            <input type="email" id="email" required>
            
            <label for="password">Password</label>
            <input type="password" id="password" required>
            
            <button type="submit">Login</button>
            <div id="error"></div>
        </form>
        <div class="link">
            Don't have an account? <a href="/signup">Sign up</a>
        </div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const error = document.getElementById('error');
            error.innerHTML = '';
            
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        email: document.getElementById('email').value,
                        password: document.getElementById('password').value
                    })
                });
                
                const data = await res.json();
                if (res.ok) {
                    window.location.href = '/';
                } else {
                    error.innerHTML = '<div class="error">' + data.error + '</div>';
                }
            } catch (e) {
                error.innerHTML = '<div class="error">Login failed. Please try again.</div>';
            }
        });
    </script>
</body>
</html>'''

SIGNUP_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
        .container { max-width: 400px; width: 100%; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { color: #2d5016; margin-bottom: 30px; text-align: center; }
        label { display: block; color: #2d5016; font-weight: bold; margin-top: 15px; margin-bottom: 5px; }
        input { width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; font-family: Georgia, serif; }
        button { width: 100%; padding: 14px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 20px; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .error { color: #721c24; background: #f8d7da; padding: 12px; border-radius: 4px; margin-top: 15px; }
        .success { color: #155724; background: #d4edda; padding: 12px; border-radius: 4px; margin-top: 15px; }
        .link { text-align: center; margin-top: 20px; color: #666; }
        .link a { color: #2d5016; font-weight: bold; text-decoration: none; }
        .link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍳 Recipe Book</h1>
        <form id="signupForm">
            <label for="email">Email</label>
            <input type="email" id="email" required>
            
            <label for="password">Password</label>
            <input type="password" id="password" required minlength="6">
            
            <label for="confirm">Confirm Password</label>
            <input type="password" id="confirm" required minlength="6">
            
            <button type="submit">Sign Up</button>
            <div id="message"></div>
        </form>
        <div class="link">
            Already have an account? <a href="/login">Login</a>
        </div>
    </div>
    
    <script>
        document.getElementById('signupForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = document.getElementById('message');
            message.innerHTML = '';
            
            const password = document.getElementById('password').value;
            const confirm = document.getElementById('confirm').value;
            
            if (password !== confirm) {
                message.innerHTML = '<div class="error">Passwords do not match</div>';
                return;
            }
            
            try {
                const res = await fetch('/api/signup', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        email: document.getElementById('email').value,
                        password: password
                    })
                });
                
                const data = await res.json();
                if (res.ok) {
                    message.innerHTML = '<div class="success">Account created! Redirecting...</div>';
                    setTimeout(() => window.location.href = '/', 1500);
                } else {
                    message.innerHTML = '<div class="error">' + data.error + '</div>';
                }
            } catch (e) {
                message.innerHTML = '<div class="error">Signup failed. Please try again.</div>';
            }
        });
    </script>
</body>
</html>'''

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
                
                <label for="url">Recipe URL (optional)</label>
                <input type="url" id="url" placeholder="https://example.com/recipe">
                
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
                
                <label for="ingredients">Ingredients * (one per line)</label>
                <textarea id="ingredients" required placeholder="1 cup flour&#10;2 eggs&#10;1/2 cup sugar"></textarea>
                
                <label for="instructions">Instructions * (one per line)</label>
                <textarea id="instructions" required placeholder="Preheat oven to 350°F&#10;Mix dry ingredients&#10;Add wet ingredients"></textarea>
                
                <label for="notes">Notes (optional)</label>
                <textarea id="notes" style="min-height: 100px;"></textarea>
                
                <button type="submit">Add Recipe</button>
                <div id="status"></div>
            </form>
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
                url: document.getElementById('url').value,
                category: document.getElementById('category').value,
                ingredients: document.getElementById('ingredients').value,
                instructions: document.getElementById('instructions').value,
                notes: document.getElementById('notes').value
            };
            
            try {
                const res = await fetch('/api/add-manual', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                
                if (res.ok) {
                    status.innerHTML = '<div class="status success">✅ Recipe added! Redirecting...</div>';
                    setTimeout(() => window.location.href = '/', 1500);
                } else {
                    const data = await res.json();
                    status.innerHTML = '<div class="status error">❌ ' + data.error + '</div>';
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
                
                <label for="url">Recipe URL (optional)</label>
                <input type="url" id="url" value="{{URL}}" placeholder="https://example.com/recipe">
                
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
                <textarea id="ingredients" required>{{INGREDIENTS}}</textarea>
                
                <label for="instructions">Instructions * (one per line)</label>
                <textarea id="instructions" required>{{INSTRUCTIONS}}</textarea>
                
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
                const response = await fetch('/api/edit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        index: parseInt(document.getElementById('recipeIndex').value),
                        title: document.getElementById('title').value,
                        url: document.getElementById('url').value,
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

SETTINGS_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings - Recipe Book</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Georgia, serif; background: #f9f7f4; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #2d5016; margin-bottom: 30px; cursor: pointer; }
        .section { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .section h2 { color: #2d5016; margin-bottom: 15px; font-size: 20px; }
        label { display: block; color: #2d5016; font-weight: bold; margin-top: 15px; margin-bottom: 5px; }
        input { width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; font-family: Georgia, serif; }
        button { padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 15px; font-weight: bold; }
        button:hover { background: #f1c40f; }
        .status { padding: 12px; border-radius: 4px; margin-top: 15px; }
        .status.success { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        .premium-badge { background: #f4d03f; color: #333; padding: 5px 10px; border-radius: 4px; font-size: 14px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1 onclick="window.location.href='/'" title="Back to main page">⚙️ Settings</h1>
        
        <div class="section">
            <h2>Personalization</h2>
            <label for="bookName">Recipe Book Name</label>
            <input type="text" id="bookName" value="{{BOOK_NAME}}" placeholder="🍳 Recipe Book">
            <button onclick="saveBookName()">Save Name</button>
            <div id="nameStatus"></div>
        </div>
        
        <div class="section">
            <h2>Account</h2>
            <p><strong>Email:</strong> {{EMAIL}}</p>
            <p style="margin-top: 10px;"><strong>Account created:</strong> {{CREATED}}</p>
            <p style="margin-top: 10px;"><strong>Total recipes:</strong> {{RECIPE_COUNT}}</p>
        </div>
        
        <div class="section">
            <h2>Premium Features</h2>
            <p>Upgrade to premium for $5 (one-time) to unlock:</p>
            <ul style="margin: 15px 0 15px 20px; line-height: 1.8;">
                <li>Custom themes (colors & fonts)</li>
                <li>Recipe sharing with friends</li>
                <li>PDF export</li>
                <li>Enhanced printing options</li>
                <li>Premium badge</li>
            </ul>
            <button style="background: #2d5016; color: white;">🌟 Upgrade to Premium - $5</button>
            <p style="margin-top: 10px; font-size: 14px; color: #666;">Coming soon!</p>
        </div>
        
        <div class="section">
            <h2>Support</h2>
            <p>Found a bug or have a feature request?</p>
            <button onclick="window.open('https://github.com/blondegedu/recipe-book/issues', '_blank')" style="background: #6c757d; color: white; margin-top: 10px;">Report Issue</button>
        </div>
        
        <div class="section">
            <h2>About</h2>
            <p><strong>Version:</strong> 1.0.0 Beta</p>
            <p style="margin-top: 10px;"><strong>Made with:</strong> Python, Love, and Recipes 🍳</p>
        </div>
    </div>
    
    <script>
        async function saveBookName() {
            const bookName = document.getElementById('bookName').value;
            const status = document.getElementById('nameStatus');
            
            try {
                const res = await fetch('/api/update-book-name', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({bookName})
                });
                
                if (res.ok) {
                    status.innerHTML = '<div class="status success">✅ Saved! Refresh to see changes.</div>';
                } else {
                    status.innerHTML = '<div class="status error">❌ Failed to save</div>';
                }
            } catch (e) {
                status.innerHTML = '<div class="status error">❌ Error: ' + e.message + '</div>';
            }
        }
    </script>
</body>
</html>'''


# Continue in next message...

# Main HTML (will be populated with user's recipe book name)
def get_main_html(user_id):
    users = load_users()
    user = users.get(user_id, {})
    book_name = user.get('book_name', '🍳 Recipe Book')
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{book_name}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Georgia, serif; background: #f9f7f4; padding: 20px; overflow-x: hidden; }}
        .container {{ max-width: 1200px; margin: 0 auto; width: 100%; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: #2d5016; word-wrap: break-word; cursor: pointer; }}
        .logout {{ padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; text-decoration: none; }}
        .logout:hover {{ background: #5a6268; }}
        .recipe-list {{ display: grid; gap: 20px; margin-top: 20px; }}
        .recipe-card {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; cursor: pointer; max-width: 100%; }}
        .recipe-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        .recipe-card h2 {{ color: #2d5016; font-size: 22px; margin-bottom: 10px; word-wrap: break-word; }}
        .recipe-full {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; margin-bottom: 20px; max-width: 100%; overflow-wrap: break-word; }}
        .recipe-full h2 {{ color: #2d5016; font-size: 28px; margin-bottom: 20px; word-wrap: break-word; }}
        .ingredients, .instructions {{ margin: 20px 0; }}
        .ingredients h3, .instructions h3 {{ color: #2d5016; margin-bottom: 15px; }}
        .ingredients li {{ padding: 8px 0; word-wrap: break-word; }}
        .instructions li {{ padding: 10px 0; margin-bottom: 10px; word-wrap: break-word; }}
        button {{ padding: 12px 24px; background: #f4d03f; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin: 10px 10px 10px 0; font-weight: bold; }}
        button:hover {{ background: #f1c40f; }}
        .btn-danger {{ background: #dc3545; color: white; }}
        .btn-danger:hover {{ background: #c82333; }}
        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .recipe-full {{ padding: 15px; }}
            button {{ padding: 10px 16px; font-size: 14px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 onclick="backToList()" style="cursor: pointer;">{book_name}</h1>
            <div>
                <a href="/settings" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; text-decoration: none; margin-right: 10px;">⚙️ Settings</a>
                <a href="/logout" class="logout">Logout</a>
            </div>
        </div>
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <input type="text" id="urlInput" placeholder="Paste recipe URL..." style="width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px; font-size: 16px; box-sizing: border-box; margin-bottom: 12px;" />
            <div style="display: flex; align-items: center; margin-bottom: 12px;">
                <button onclick="addRecipe()" id="addBtn" style="flex: 1; padding: 12px; font-size: 16px; margin: 0;">Add from URL</button>
                <span style="color: #999; font-size: 14px; padding: 0 15px; text-align: center;">or</span>
                <button onclick="window.location.href='/add-manual'" style="flex: 1; padding: 12px; font-size: 16px; margin: 0;">Add Manually</button>
            </div>
            <div id="status"></div>
            <p style="font-size: 13px; color: #666; margin-top: 10px;">
                💡 If a URL doesn't work, try <a href="https://www.justtherecipe.com/" target="_blank" style="color: #8b4513;">JustTheRecipe.com</a> or <a href="https://video2recipe.com/" target="_blank" style="color: #8b4513;">Video2Recipe.com</a> first
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
        
        async function loadRecipes() {{
            const res = await fetch('/api/recipes');
            recipes = await res.json();
            displayRecipes();
        }}
        
        function displayRecipes() {{
            const container = document.getElementById('recipes');
            const search = document.getElementById('searchBox').value.toLowerCase();
            const sort = document.getElementById('sortBox').value;
            
            let filtered = recipes.filter(r => 
                r.title.toLowerCase().includes(search) ||
                (r.ingredients || []).some(i => i.toLowerCase().includes(search)) ||
                (r.instructions || []).some(i => i.toLowerCase().includes(search)) ||
                (r.category || '').toLowerCase().includes(search)
            );
            
            const categoryOrder = ['Breakfast', 'Lunch', 'Dinner', 'Snack', 'Dessert', 'Condiment', 'Other'];
            
            if (sort === 'date-newest') {{
                filtered.sort((a, b) => new Date(b.date) - new Date(a.date));
            }} else if (sort === 'date-oldest') {{
                filtered.sort((a, b) => new Date(a.date) - new Date(b.date));
            }} else if (sort === 'alphabetical') {{
                filtered.sort((a, b) => a.title.localeCompare(b.title));
            }} else if (sort === 'category') {{
                filtered.sort((a, b) => {{
                    const aIdx = categoryOrder.indexOf(a.category || 'Other');
                    const bIdx = categoryOrder.indexOf(b.category || 'Other');
                    return aIdx - bIdx;
                }});
            }}
            
            if (filtered.length === 0) {{
                container.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">No recipes found. Add your first recipe!</p>';
                return;
            }}
            
            container.innerHTML = '<div class="recipe-list">' + 
                filtered.map((recipe, index) => `
                    <div class="recipe-card" onclick="showRecipe(${{recipes.indexOf(recipe)}})">
                        <h2>${{recipe.title}}</h2>
                        <p style="color: #666; margin-top: 5px;">${{recipe.category || 'Other'}}</p>
                    </div>
                `).join('') + 
            '</div>';
        }}
        
        function filterRecipes() {{
            displayRecipes();
        }}
        
        function showRecipe(index) {{
            const recipe = recipes[index];
            const container = document.getElementById('recipes');
            
            const ingredients = (recipe.ingredients || []).length 
                ? '<ul>' + recipe.ingredients.map(i => `<li>${{i}}</li>`).join('') + '</ul>'
                : '<p>No ingredients</p>';
            
            const instructions = (recipe.instructions || []).length
                ? '<ol>' + recipe.instructions.map(i => `<li>${{i}}</li>`).join('') + '</ol>'
                : '<p>No instructions</p>';
            
            container.innerHTML = `
                <div class="recipe-full">
                    <h2 onclick="editTitle(${{index}})" style="cursor: pointer;" title="Click to rename">${{recipe.title}}</h2>
                    <div style="margin: 20px 0;">
                        <label><strong>Category:</strong></label>
                        <select id="category-input-${{index}}" onchange="saveCategory(${{index}})" style="padding: 8px; border: 2px solid #d4c5b9; border-radius: 4px; margin-left: 10px; width: 200px;">
                            <option value="">Select category...</option>
                            <option value="Breakfast" ${{recipe.category === 'Breakfast' ? 'selected' : ''}}>Breakfast</option>
                            <option value="Lunch" ${{recipe.category === 'Lunch' ? 'selected' : ''}}>Lunch</option>
                            <option value="Dinner" ${{recipe.category === 'Dinner' ? 'selected' : ''}}>Dinner</option>
                            <option value="Snack" ${{recipe.category === 'Snack' ? 'selected' : ''}}>Snack</option>
                            <option value="Dessert" ${{recipe.category === 'Dessert' ? 'selected' : ''}}>Dessert</option>
                            <option value="Condiment" ${{recipe.category === 'Condiment' ? 'selected' : ''}}>Condiment</option>
                            <option value="Other" ${{recipe.category === 'Other' ? 'selected' : ''}}>Other</option>
                        </select>
                    </div>
                    <div class="ingredients">
                        <h3>Ingredients</h3>
                        ${{ingredients}}
                    </div>
                    <div class="instructions">
                        <h3>Instructions</h3>
                        ${{instructions}}
                    </div>
                    <div style="margin: 20px 0;">
                        <label><strong>Notes:</strong></label><br/>
                        <textarea id="notes-input-${{index}}" 
                                  placeholder="Add your notes here..." 
                                  style="width: 100%; min-height: 100px; padding: 10px; border: 2px solid #d4c5b9; border-radius: 4px; margin-top: 10px; font-family: Georgia, serif; font-size: 14px;">${{recipe.notes || ''}}</textarea>
                        <button onclick="saveNotes(${{index}})" style="padding: 8px 16px; margin-top: 10px;">Save Notes</button>
                    </div>
                    <button onclick="backToList()">← Back to Recipes</button>
                    <button onclick="window.location.href='/edit/${{index}}'">Edit Recipe</button>
                    <button onclick="printRecipe(${{index}})">🖨️ Print</button>
                    ${{recipe.url ? `<button onclick="window.open('${{recipe.url}}', '_blank')" style="background: #2d5016; color: white;">View Original Recipe</button>` : ''}}
                    <button class="btn-danger" onclick="deleteRecipe(${{index}})">Delete Recipe</button>
                </div>
            `;
        }}
        
        function backToList() {{
            displayRecipes();
        }}
        
        async function addRecipe() {{
            const url = document.getElementById('urlInput').value.trim();
            const btn = document.getElementById('addBtn');
            const status = document.getElementById('status');
            
            if (!url) return;
            
            btn.disabled = true;
            btn.textContent = 'Adding...';
            status.innerHTML = '<p style="color: #666;">Extracting recipe...</p>';
            
            try {{
                const res = await fetch('/api/add', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{url}})
                }});
                
                if (res.ok) {{
                    await loadRecipes();
                    document.getElementById('urlInput').value = '';
                    status.innerHTML = '<p style="color: #155724;">✅ Recipe added!</p>';
                    setTimeout(() => status.innerHTML = '', 3000);
                }} else {{
                    const data = await res.json();
                    status.innerHTML = '<p style="color: #721c24;">❌ ' + data.error + '</p>';
                }}
                
                btn.disabled = false;
                btn.textContent = 'Add from URL';
            }} catch (e) {{
                status.innerHTML = '<p style="color: #721c24;">❌ Error: ' + e.message + '</p>';
                btn.disabled = false;
                btn.textContent = 'Add from URL';
            }}
        }}
        
        async function saveCategory(index) {{
            const category = document.getElementById(`category-input-${{index}}`).value;
            await fetch('/api/set-category', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{index, category}})
            }});
            recipes[index].category = category;
        }}
        
        async function saveNotes(index) {{
            const notes = document.getElementById(`notes-input-${{index}}`).value;
            await fetch('/api/set-notes', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{index, notes}})
            }});
            recipes[index].notes = notes;
            alert('Notes saved!');
        }}
        
        async function editTitle(index) {{
            const newTitle = prompt('Enter new title:', recipes[index].title);
            if (newTitle && newTitle.trim()) {{
                await fetch('/api/rename', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{index, title: newTitle.trim()}})
                }});
                recipes[index].title = newTitle.trim();
                showRecipe(index);
            }}
        }}
        
        async function deleteRecipe(index) {{
            if (!confirm('Delete this recipe?')) return;
            
            await fetch('/api/delete', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{index}})
            }});
            
            await loadRecipes();
        }}
        
        function printRecipe(index) {{
            window.open('/print/' + index, '_blank');
        }}
        
        loadRecipes();
    </script>
</body>
</html>'''


class RecipeHandler(BaseHTTPRequestHandler):
    def get_session_token(self):
        cookies = self.headers.get('Cookie', '')
        for cookie in cookies.split(';'):
            cookie = cookie.strip()
            if cookie.startswith('session='):
                return cookie.split('=')[1]
        return None
    
    def set_session_cookie(self, session_token):
        expiry = datetime.now() + SESSION_DURATION
        self.send_header('Set-Cookie', f'session={session_token}; Path=/; HttpOnly; SameSite=Lax; Expires={expiry.strftime("%a, %d %b %Y %H:%M:%S GMT")}')
    
    def require_auth(self):
        session_token = self.get_session_token()
        user_id = validate_session(session_token)
        if not user_id:
            self.send_response(302)
            self.send_header('Location', '/login')
            self.end_headers()
            return None
        return user_id
    
    def get_print_html(self, recipe):
        ingredients_html = '<ul>' + ''.join(f'<li>{i}</li>' for i in recipe.get('ingredients', [])) + '</ul>'
        instructions_html = '<ol>' + ''.join(f'<li>{i}</li>' for i in recipe.get('instructions', [])) + '</ol>'
        
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{recipe['title']} - Print</title>
    <style>
        @media print {{
            body {{ margin: 0; padding: 20px; }}
            .no-print {{ display: none; }}
        }}
        body {{ font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2d5016; margin-bottom: 10px; }}
        h2 {{ color: #2d5016; margin-top: 30px; margin-bottom: 15px; }}
        ul, ol {{ margin-left: 20px; }}
        li {{ margin-bottom: 8px; line-height: 1.6; }}
        .notes {{ margin-top: 30px; padding: 15px; background: #f9f7f4; border-radius: 4px; }}
        button {{ padding: 10px 20px; background: #f4d03f; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-bottom: 20px; }}
        button:hover {{ background: #f1c40f; }}
    </style>
</head>
<body>
    <button class="no-print" onclick="window.print()">🖨️ Print Recipe</button>
    <h1>{recipe['title']}</h1>
    <p><strong>Category:</strong> {recipe.get('category', 'Other')}</p>
    <h2>Ingredients</h2>
    {ingredients_html}
    <h2>Instructions</h2>
    {instructions_html}
    {f'<div class="notes"><strong>Notes:</strong><br>{recipe.get("notes", "")}</div>' if recipe.get('notes') else ''}
</body>
</html>'''
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/login':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(LOGIN_HTML.encode())
        
        elif path == '/signup':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(SIGNUP_HTML.encode())
        
        elif path == '/logout':
            session_token = self.get_session_token()
            if session_token:
                sessions = load_sessions()
                if session_token in sessions:
                    del sessions[session_token]
                    save_sessions(sessions)
            self.send_response(302)
            self.send_header('Set-Cookie', 'session=; Path=/; HttpOnly; Max-Age=0')
            self.send_header('Location', '/login')
            self.end_headers()
        
        elif path == '/':
            user_id = self.require_auth()
            if not user_id:
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(get_main_html(user_id).encode())
        
        elif path == '/add-manual':
            user_id = self.require_auth()
            if not user_id:
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(MANUAL_FORM_HTML.encode())
        
        elif path == '/settings':
            user_id = self.require_auth()
            if not user_id:
                return
            users = load_users()
            user_email = None
            for email, user_data in users.items():
                if user_data['user_id'] == user_id:
                    user_email = email
                    user = user_data
                    break
            
            recipes = load_recipes(user_id)
            settings_html = SETTINGS_HTML.replace('{{BOOK_NAME}}', user.get('book_name', '🍳 Recipe Book'))
            settings_html = settings_html.replace('{{EMAIL}}', user_email or 'Unknown')
            settings_html = settings_html.replace('{{CREATED}}', user.get('created', 'Unknown')[:10])
            settings_html = settings_html.replace('{{RECIPE_COUNT}}', str(len(recipes)))
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(settings_html.encode())
        
        elif path.startswith('/edit/'):
            user_id = self.require_auth()
            if not user_id:
                return
            try:
                recipe_index = int(path.split('/')[-1])
                recipes = load_recipes(user_id)
                if 0 <= recipe_index < len(recipes):
                    recipe = recipes[recipe_index]
                    edit_html = EDIT_FORM_HTML.replace('{{RECIPE_INDEX}}', str(recipe_index))
                    edit_html = edit_html.replace('{{TITLE}}', recipe['title'])
                    edit_html = edit_html.replace('{{URL}}', recipe.get('url', ''))
                    edit_html = edit_html.replace('{{CATEGORY}}', recipe['category'])
                    edit_html = edit_html.replace('{{INGREDIENTS}}', '\n'.join(recipe['ingredients']))
                    edit_html = edit_html.replace('{{INSTRUCTIONS}}', '\n'.join(recipe['instructions']))
                    edit_html = edit_html.replace('{{NOTES}}', recipe.get('notes', ''))
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(edit_html.encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            except:
                self.send_response(404)
                self.end_headers()
        
        elif path.startswith('/print/'):
            user_id = self.require_auth()
            if not user_id:
                return
            try:
                recipe_index = int(path.split('/')[-1])
                recipes = load_recipes(user_id)
                if 0 <= recipe_index < len(recipes):
                    recipe = recipes[recipe_index]
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(self.get_print_html(recipe).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            except:
                self.send_response(404)
                self.end_headers()
        
        elif path == '/api/recipes':
            user_id = self.require_auth()
            if not user_id:
                return
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(load_recipes(user_id)).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/api/signup':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            
            if not email or not password:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Email and password required'}).encode())
                return
            
            if len(password) < 6:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Password must be at least 6 characters'}).encode())
                return
            
            users = load_users()
            if email in users:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Email already registered'}).encode())
                return
            
            user_id = secrets.token_urlsafe(16)
            users[email] = {
                'user_id': user_id,
                'password': hash_password(password),
                'book_name': '🍳 Recipe Book',
                'created': datetime.now().isoformat()
            }
            save_users(users)
            
            # Create empty recipe file
            save_recipes(user_id, [])
            
            # Create session
            session_token = create_session(user_id)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.set_session_cookie(session_token)
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif path == '/api/login':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            
            users = load_users()
            user = users.get(email)
            
            if not user or user['password'] != hash_password(password):
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid email or password'}).encode())
                return
            
            session_token = create_session(user['user_id'])
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.set_session_cookie(session_token)
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif path == '/api/add':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            url = data.get('url', '')
            
            try:
                recipe_data = extract_recipe(url)
                recipe = {
                    'title': recipe_data['title'],
                    'category': 'Other',
                    'ingredients': recipe_data['ingredients'],
                    'instructions': recipe_data['instructions'],
                    'notes': '',
                    'url': url,
                    'date': datetime.now().isoformat()
                }
                
                recipes = load_recipes(user_id)
                recipes.append(recipe)
                save_recipes(user_id, recipes)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif path == '/api/add-manual':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            
            recipe = {
                'title': data.get('title', 'Untitled Recipe'),
                'category': data.get('category', 'Other'),
                'ingredients': [i.strip() for i in data.get('ingredients', '').split('\n') if i.strip()],
                'instructions': [i.strip() for i in data.get('instructions', '').split('\n') if i.strip()],
                'notes': data.get('notes', ''),
                'url': data.get('url', ''),
                'date': datetime.now().isoformat()
            }
            
            recipes = load_recipes(user_id)
            recipes.append(recipe)
            save_recipes(user_id, recipes)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif path == '/api/set-notes':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            notes = data.get('notes', '')
            
            recipes = load_recipes(user_id)
            if 0 <= index < len(recipes):
                recipes[index]['notes'] = notes
                save_recipes(user_id, recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif path == '/api/set-category':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            category = data.get('category', '')
            
            recipes = load_recipes(user_id)
            if 0 <= index < len(recipes):
                recipes[index]['category'] = category
                save_recipes(user_id, recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif path == '/api/rename':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            title = data.get('title', '')
            
            recipes = load_recipes(user_id)
            if 0 <= index < len(recipes):
                recipes[index]['title'] = title
                save_recipes(user_id, recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif path == '/api/delete':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            
            recipes = load_recipes(user_id)
            if 0 <= index < len(recipes):
                recipes.pop(index)
                save_recipes(user_id, recipes)
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
        
        elif path == '/api/edit':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index', -1)
            
            recipes = load_recipes(user_id)
            if 0 <= index < len(recipes):
                recipes[index]['title'] = data.get('title', '')
                recipes[index]['url'] = data.get('url', '')
                recipes[index]['category'] = data.get('category', 'Other')
                recipes[index]['ingredients'] = [i.strip() for i in data.get('ingredients', '').split('\n') if i.strip()]
                recipes[index]['instructions'] = [i.strip() for i in data.get('instructions', '').split('\n') if i.strip()]
                recipes[index]['notes'] = data.get('notes', '')
                save_recipes(user_id, recipes)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            else:
                self.send_response(400)
                self.end_headers()
        
        elif path == '/api/update-book-name':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            book_name = data.get('bookName', '🍳 Recipe Book')
            
            users = load_users()
            for email, user_data in users.items():
                if user_data['user_id'] == user_id:
                    user_data['book_name'] = book_name
                    save_users(users)
                    break
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress log messages


if __name__ == '__main__':
    PORT = 8080
    server = HTTPServer(('0.0.0.0', PORT), RecipeHandler)
    print(f'🍳 Multi-user Recipe Book server running on http://localhost:{PORT}')
    print(f'📝 Sign up at http://localhost:{PORT}/signup')
    server.serve_forever()
