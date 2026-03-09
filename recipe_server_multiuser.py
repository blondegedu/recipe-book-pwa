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
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.enums import TA_LEFT

# File paths
USERS_FILE = 'users.json'
SESSIONS_FILE = 'sessions.json'
RECIPES_DIR = 'user_recipes'
SHARED_FILE = 'shared_recipes.json'

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

def load_shared():
    if os.path.exists(SHARED_FILE):
        with open(SHARED_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_shared(shared):
    with open(SHARED_FILE, 'w') as f:
        json.dump(shared, f, indent=2)

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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try JSON-LD first (most reliable)
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
                
                # Handle array of items
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Recipe':
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
                                text = inst.get('text', '') or inst.get('name', '')
                                if text:
                                    instructions.append(text)
                    
                    # Only return if we have both ingredients AND instructions
                    if ingredients and instructions:
                        return {
                            'title': data.get('name', 'Untitled Recipe'),
                            'ingredients': [i for i in ingredients if i],
                            'instructions': [i for i in instructions if i]
                        }
            except:
                continue
        
        # Fallback: Try common recipe HTML structures
        title = None
        for selector in ['h1.recipe-title', 'h1.headline', 'h1', 'h2.recipe-title', '.recipe-title']:
            elem = soup.select_one(selector)
            if elem:
                title = elem.get_text().strip()
                break
        
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip().split('|')[0].split('-')[0].strip()
            else:
                title = 'Untitled Recipe'
        
        # Find ingredients with better selectors
        ingredients = []
        for selector in ['.recipe-ingredients li', '.ingredients li', '[itemprop="recipeIngredient"]', 'li[itemprop="ingredients"]']:
            items = soup.select(selector)
            if items:
                ingredients = [item.get_text().strip() for item in items if item.get_text().strip()]
                break
        
        # Fallback: look for lists with measurements, but exclude junk
        if not ingredients:
            exclude_words = ['instagram', 'facebook', 'pinterest', 'twitter', 'subscribe', 'newsletter', 'comment', 'reply', 'share']
            for tag in soup.find_all('li'):
                text = tag.get_text().strip()
                # Must have measurements and not be social/comment junk
                if (any(word in text.lower() for word in ['cup', 'tablespoon', 'teaspoon', 'tbsp', 'tsp', 'oz', 'lb', 'gram', 'kg', 'ml']) 
                    and not any(word in text.lower() for word in exclude_words)
                    and len(text) < 200 and len(text) > 5):
                    ingredients.append(text)
                    if len(ingredients) >= 30:
                        break
        
        # Find instructions with better selectors
        instructions = []
        for selector in ['.recipe-instructions li', '.instructions li', '.recipe-steps li', '[itemprop="recipeInstructions"] li', 'ol li']:
            items = soup.select(selector)
            if items and len(items) > 2:  # Must have at least 3 steps
                instructions = [item.get_text().strip() for item in items if item.get_text().strip()]
                break
        
        # Fallback: look for paragraphs/lists with cooking verbs, but exclude junk
        if not instructions:
            exclude_words = ['instagram', 'facebook', 'pinterest', 'twitter', 'subscribe', 'newsletter', 'comment', 'reply', 'share', 'recipe', 'click here', 'read more']
            for tag in soup.find_all(['li', 'p']):
                text = tag.get_text().strip()
                # Must have cooking verbs and not be social/comment/link junk
                if (any(word in text.lower() for word in ['heat', 'cook', 'bake', 'mix', 'add', 'stir', 'place', 'combine', 'whisk', 'pour'])
                    and not any(word in text.lower() for word in exclude_words)
                    and len(text) > 20 and len(text) < 500
                    and not text.startswith('http')):  # Exclude URLs
                    instructions.append(text)
                    if len(instructions) >= 20:
                        break
        
        return {
            'title': title,
            'ingredients': ingredients[:30],  # Limit
            'instructions': instructions[:20]  # Limit
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
            
            // Try to detect sections
            let title = '';
            let ingredients = [];
            let instructions = [];
            
            let currentSection = 'unknown';
            
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                const lower = line.toLowerCase();
                
                // Check for section headers
                if (lower.includes('ingredient')) {
                    currentSection = 'ingredients';
                    continue;
                } else if (lower.includes('instruction') || lower.includes('direction') || lower.includes('step')) {
                    currentSection = 'instructions';
                    continue;
                }
                
                // Detect ingredients by pattern (measurements, fractions)
                const hasIngredientPattern = /\\d|cup|tbsp|tsp|tablespoon|teaspoon|oz|lb|gram|kg|ml|liter|\\//.test(line);
                
                // Detect instructions by pattern (starts with dash, action verbs)
                const hasInstructionPattern = /^-|^\\d+\\.|mix|add|bake|cook|heat|stir|combine|fold|refrigerate|preheat|place/i.test(line);
                
                if (currentSection === 'unknown') {
                    // First line is likely title
                    if (!title && i === 0) {
                        title = line;
                    } else if (hasIngredientPattern && !hasInstructionPattern) {
                        currentSection = 'ingredients';
                        ingredients.push(line);
                    } else if (hasInstructionPattern) {
                        currentSection = 'instructions';
                        instructions.push(line.replace(/^-\\s*/, ''));
                    }
                } else if (currentSection === 'ingredients') {
                    if (hasInstructionPattern && !hasIngredientPattern) {
                        currentSection = 'instructions';
                        instructions.push(line.replace(/^-\\s*/, ''));
                    } else {
                        ingredients.push(line);
                    }
                } else if (currentSection === 'instructions') {
                    instructions.push(line.replace(/^-\\s*/, ''));
                }
            }
            
            // Fill form
            document.getElementById('title').value = title || 'Untitled Recipe';
            document.getElementById('ingredients').value = ingredients.join('\\n');
            document.getElementById('instructions').value = instructions.join('\\n');
            
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
            <h2>Theme Customization</h2>
            <p style="margin-bottom: 15px;">Personalize your recipe book's appearance:</p>
            
            <label for="primaryColor">Primary Color (buttons)</label>
            <input type="color" id="primaryColor" value="{{PRIMARY_COLOR}}" style="width: 100px; height: 40px; cursor: pointer;">
            
            <label for="textColor">Text Color</label>
            <input type="color" id="textColor" value="{{TEXT_COLOR}}" style="width: 100px; height: 40px; cursor: pointer;">
            
            <label for="fontFamily">Font</label>
            <select id="fontFamily" style="width: 100%; padding: 12px; border: 2px solid #d4c5b9; border-radius: 4px;">
                <option value="Georgia, serif">Georgia (Classic)</option>
                <option value="'Courier New', monospace">Courier New (Typewriter)</option>
                <option value="Arial, sans-serif">Arial (Modern)</option>
                <option value="'Times New Roman', serif">Times New Roman (Traditional)</option>
                <option value="Verdana, sans-serif">Verdana (Clean)</option>
            </select>
            
            <button onclick="saveTheme()">Save Theme</button>
            <button onclick="resetTheme()" style="background: #6c757d; color: white; margin-left: 10px;">Reset to Default</button>
            <div id="themeStatus"></div>
        </div>
        
        <div class="section">
            <h2>Premium Features</h2>
            <p>You have access to all premium features! 🎉</p>
            <ul style="margin: 15px 0 15px 20px; line-height: 1.8;">
                <li>✅ Custom themes (colors & fonts)</li>
                <li>✅ Recipe sharing with friends</li>
                <li>✅ PDF export</li>
                <li>✅ Premium badge</li>
            </ul>
            <p style="margin-top: 10px; font-size: 14px; color: #666;">Thank you for using Recipe Book!</p>
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
        
        async function saveTheme() {
            const theme = {
                primaryColor: document.getElementById('primaryColor').value,
                textColor: document.getElementById('textColor').value,
                fontFamily: document.getElementById('fontFamily').value
            };
            const status = document.getElementById('themeStatus');
            
            try {
                const res = await fetch('/api/update-theme', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(theme)
                });
                
                if (res.ok) {
                    status.innerHTML = '<div class="status success">✅ Theme saved! Refresh to see changes.</div>';
                } else {
                    status.innerHTML = '<div class="status error">❌ Failed to save theme</div>';
                }
            } catch (e) {
                status.innerHTML = '<div class="status error">❌ Error: ' + e.message + '</div>';
            }
        }
        
        async function resetTheme() {
            const status = document.getElementById('themeStatus');
            
            try {
                const res = await fetch('/api/reset-theme', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });
                
                if (res.ok) {
                    status.innerHTML = '<div class="status success">✅ Theme reset! Refresh to see changes.</div>';
                    document.getElementById('primaryColor').value = '#f4d03f';
                    document.getElementById('textColor').value = '#2d5016';
                    document.getElementById('fontFamily').value = 'Georgia, serif';
                } else {
                    status.innerHTML = '<div class="status error">❌ Failed to reset theme</div>';
                }
            } catch (e) {
                status.innerHTML = '<div class="status error">❌ Error: ' + e.message + '</div>';
            }
        }
        
        // Set current font selection
        document.getElementById('fontFamily').value = '{{FONT_FAMILY}}';
    </script>
</body>
</html>'''


# Continue in next message...

# Main HTML (will be populated with user's recipe book name)
def get_main_html(user_id):
    users = load_users()
    user_email = None
    user = None
    for email, user_data in users.items():
        if user_data['user_id'] == user_id:
            user = user_data
            break
    
    if not user:
        user = {}
    
    book_name = user.get('book_name', '🍳 Recipe Book')
    theme = user.get('theme', {})
    primary_color = theme.get('primaryColor', '#f4d03f')
    primary_hover = theme.get('primaryColor', '#f1c40f')  # Slightly darker
    text_color = theme.get('textColor', '#2d5016')
    font_family = theme.get('fontFamily', 'Georgia, serif')
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{book_name}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <link rel="manifest" href="/manifest.json">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: {font_family}; background: #f9f7f4; padding: 20px; overflow-x: hidden; }}
        .container {{ max-width: 1200px; margin: 0 auto; width: 100%; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: {text_color}; word-wrap: break-word; cursor: pointer; }}
        .logout {{ padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; text-decoration: none; }}
        .logout:hover {{ background: #5a6268; }}
        .recipe-list {{ display: grid; gap: 20px; margin-top: 20px; }}
        .recipe-card {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; cursor: pointer; max-width: 100%; }}
        .recipe-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        .recipe-card h2 {{ color: {text_color}; font-size: 22px; margin-bottom: 10px; word-wrap: break-word; }}
        .recipe-full {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; margin-bottom: 20px; max-width: 100%; overflow-wrap: break-word; }}
        .recipe-full h2 {{ color: {text_color}; font-size: 28px; margin-bottom: 20px; word-wrap: break-word; }}
        .ingredients, .instructions {{ margin: 20px 0; }}
        .ingredients h3, .instructions h3 {{ color: {text_color}; margin-bottom: 15px; }}
        .ingredients li {{ padding: 8px 0; word-wrap: break-word; }}
        .instructions li {{ padding: 10px 0; margin-bottom: 10px; word-wrap: break-word; }}
        button {{ padding: 12px 24px; background: {primary_color}; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin: 10px 10px 10px 0; font-weight: bold; }}
        button:hover {{ background: {primary_hover}; }}
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
            <div style="display: flex; gap: 10px; align-items: center;">
                <a href="https://ko-fi.com/yourname" target="_blank" style="padding: 10px 15px; background: #ff5e5b; color: white; border: none; border-radius: 50%; cursor: pointer; font-size: 20px; text-decoration: none; display: flex; align-items: center; justify-content: center; width: 45px; height: 45px;" title="Support">☕</a>
                <a href="/settings" style="padding: 10px 15px; background: #6c757d; color: white; border: none; border-radius: 50%; cursor: pointer; font-size: 20px; text-decoration: none; display: flex; align-items: center; justify-content: center; width: 45px; height: 45px;" title="Settings">⚙️</a>
                <a href="/logout" style="padding: 10px 15px; background: #6c757d; color: white; border: none; border-radius: 50%; cursor: pointer; font-size: 20px; text-decoration: none; display: flex; align-items: center; justify-content: center; width: 45px; height: 45px;" title="Logout">🚪</a>
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
                    <button onclick="shareRecipe(${{index}})">🔗 Share</button>
                    <button onclick="window.location.href='/pdf/${{index}}'">📄 PDF</button>
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
                    if (data.blocked) {{
                        status.innerHTML = `
                            <div style="background: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 15px; margin: 10px 0;">
                                <p style="color: #856404; margin: 0 0 10px 0; font-weight: bold;">⚠️ ${{data.error}}</p>
                                <p style="color: #856404; margin: 0 0 10px 0;">${{data.suggestion}}</p>
                                <button onclick="window.location.href='/add-manual'" style="background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
                                    📝 Add Recipe Manually
                                </button>
                            </div>
                        `;
                    }} else {{
                        status.innerHTML = '<p style="color: #721c24;">❌ ' + data.error + '</p>';
                    }}
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
        
        async function shareRecipe(index) {{
            try {{
                const res = await fetch('/api/share', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{index}})
                }});
                const data = await res.json();
                if (data.shareId) {{
                    const shareUrl = window.location.origin + '/shared/' + data.shareId;
                    navigator.clipboard.writeText(shareUrl);
                    alert('Share link copied to clipboard!\\n\\n' + shareUrl);
                }}
            }} catch (err) {{
                alert('Failed to create share link');
            }}
        }}
        
        // Register service worker for offline support
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/service-worker.js')
                .then(reg => console.log('Service Worker registered'))
                .catch(err => console.log('Service Worker registration failed'));
        }}
        
        // Show offline indicator
        window.addEventListener('online', () => {{
            const indicator = document.getElementById('offline-indicator');
            if (indicator) indicator.remove();
        }});
        
        window.addEventListener('offline', () => {{
            if (!document.getElementById('offline-indicator')) {{
                const div = document.createElement('div');
                div.id = 'offline-indicator';
                div.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; background: #dc3545; color: white; padding: 10px; text-align: center; z-index: 9999;';
                div.textContent = '⚠️ You are offline - Some features may be limited';
                document.body.prepend(div);
            }}
        }});
        
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
    
    def get_shared_html(self, recipe):
        ingredients_html = '<ul>' + ''.join(f'<li>{i}</li>' for i in recipe.get('ingredients', [])) + '</ul>'
        instructions_html = '<ol>' + ''.join(f'<li>{i}</li>' for i in recipe.get('instructions', [])) + '</ol>'
        
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{recipe['title']}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🍳</text></svg>">
    <style>
        body {{ font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f9f7f4; }}
        .recipe {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; }}
        h1 {{ color: #2d5016; margin-bottom: 10px; }}
        h2 {{ color: #2d5016; margin-top: 30px; margin-bottom: 15px; }}
        ul, ol {{ margin-left: 20px; }}
        li {{ margin-bottom: 8px; line-height: 1.6; }}
        .notes {{ margin-top: 30px; padding: 15px; background: #f9f7f4; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="recipe">
        <h1>{recipe['title']}</h1>
        <p><strong>Category:</strong> {recipe.get('category', 'Other')}</p>
        <h2>Ingredients</h2>
        {ingredients_html}
        <h2>Instructions</h2>
        {instructions_html}
        {f'<div class="notes"><strong>Notes:</strong><br>{recipe.get("notes", "")}</div>' if recipe.get('notes') else ''}
    </div>
</body>
</html>'''
    
    def generate_pdf(self, recipe):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, textColor='#2d5016')
        story.append(Paragraph(recipe['title'], title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Category
        if recipe.get('category'):
            story.append(Paragraph(f"<b>Category:</b> {recipe['category']}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Ingredients
        story.append(Paragraph('<b>Ingredients</b>', styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        if recipe.get('ingredients'):
            items = [ListItem(Paragraph(ing, styles['Normal'])) for ing in recipe['ingredients']]
            story.append(ListFlowable(items, bulletType='bullet'))
        story.append(Spacer(1, 0.2*inch))
        
        # Instructions
        story.append(Paragraph('<b>Instructions</b>', styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        if recipe.get('instructions'):
            items = [ListItem(Paragraph(inst, styles['Normal'])) for inst in recipe['instructions']]
            story.append(ListFlowable(items, bulletType='1'))
        story.append(Spacer(1, 0.2*inch))
        
        # Notes
        if recipe.get('notes'):
            story.append(Paragraph('<b>Notes</b>', styles['Heading2']))
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph(recipe['notes'], styles['Normal']))
        
        doc.build(story)
        return buffer.getvalue()
    
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
            theme = user.get('theme', {})
            settings_html = SETTINGS_HTML.replace('{{BOOK_NAME}}', user.get('book_name', '🍳 Recipe Book'))
            settings_html = settings_html.replace('{{EMAIL}}', user_email or 'Unknown')
            settings_html = settings_html.replace('{{CREATED}}', user.get('created', 'Unknown')[:10])
            settings_html = settings_html.replace('{{RECIPE_COUNT}}', str(len(recipes)))
            settings_html = settings_html.replace('{{PRIMARY_COLOR}}', theme.get('primaryColor', '#f4d03f'))
            settings_html = settings_html.replace('{{TEXT_COLOR}}', theme.get('textColor', '#2d5016'))
            settings_html = settings_html.replace('{{FONT_FAMILY}}', theme.get('fontFamily', 'Georgia, serif'))
            
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
        
        elif path.startswith('/shared/'):
            share_id = path.split('/')[-1]
            shared = load_shared()
            
            if share_id not in shared:
                self.send_response(404)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<h1>Recipe not found</h1>')
                return
            
            recipe = shared[share_id]['recipe']
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.get_shared_html(recipe).encode())
        
        elif path.startswith('/pdf/'):
            user_id = self.require_auth()
            if not user_id:
                return
            try:
                recipe_index = int(path.split('/')[-1])
                recipes = load_recipes(user_id)
                if 0 <= recipe_index < len(recipes):
                    recipe = recipes[recipe_index]
                    pdf_data = self.generate_pdf(recipe)
                    filename = re.sub(r'[^\w\s-]', '', recipe['title']).strip().replace(' ', '_')
                    self.send_response(200)
                    self.send_header('Content-type', 'application/pdf')
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}.pdf"')
                    self.end_headers()
                    self.wfile.write(pdf_data)
                else:
                    self.send_response(404)
                    self.end_headers()
            except Exception as e:
                print(f"PDF error: {e}")
                self.send_response(500)
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
        
        elif path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'version': '1.0'}).encode())
        
        elif path == '/manifest.json':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            with open('manifest.json', 'rb') as f:
                self.wfile.write(f.read())
        
        elif path == '/service-worker.js':
            self.send_response(200)
            self.send_header('Content-type', 'application/javascript')
            self.end_headers()
            with open('service-worker.js', 'rb') as f:
                self.wfile.write(f.read())
        
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
                
                # Check if extraction was poor (missing data or junk)
                if not recipe_data.get('ingredients') or not recipe_data.get('instructions') or len(recipe_data.get('ingredients', [])) < 2:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Could not extract recipe properly from this site.',
                        'blocked': True,
                        'suggestion': 'This site may not have proper recipe formatting. Try Manual Add - copy/paste the recipe!'
                    }).encode())
                    return
                
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
                error_msg = str(e)
                # Check if site is blocking us
                if '402' in error_msg or '403' in error_msg or 'Payment Required' in error_msg or 'Forbidden' in error_msg:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'This site blocks automated recipe extraction.',
                        'blocked': True,
                        'suggestion': 'Try the Manual Add button instead - just copy/paste the recipe and use Quick Paste!'
                    }).encode())
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': error_msg}).encode())
        
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
        
        elif path == '/api/update-theme':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            theme = {
                'primaryColor': data.get('primaryColor', '#f4d03f'),
                'textColor': data.get('textColor', '#2d5016'),
                'fontFamily': data.get('fontFamily', 'Georgia, serif')
            }
            
            users = load_users()
            for email, user_data in users.items():
                if user_data['user_id'] == user_id:
                    user_data['theme'] = theme
                    save_users(users)
                    break
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif path == '/api/reset-theme':
            user_id = self.require_auth()
            if not user_id:
                return
            
            users = load_users()
            for email, user_data in users.items():
                if user_data['user_id'] == user_id:
                    user_data['theme'] = {
                        'primaryColor': '#f4d03f',
                        'textColor': '#2d5016',
                        'fontFamily': 'Georgia, serif'
                    }
                    save_users(users)
                    break
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif path == '/api/share':
            user_id = self.require_auth()
            if not user_id:
                return
            
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))
            index = data.get('index')
            
            recipes = load_recipes(user_id)
            if index < 0 or index >= len(recipes):
                self.send_response(400)
                self.end_headers()
                return
            
            recipe = recipes[index]
            share_id = secrets.token_urlsafe(16)
            
            shared = load_shared()
            shared[share_id] = {
                'user_id': user_id,
                'recipe': recipe,
                'created': datetime.now().isoformat()
            }
            save_shared(shared)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'shareId': share_id}).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress log messages


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    HOST = os.environ.get('HOST', '0.0.0.0')
    server = HTTPServer((HOST, PORT), RecipeHandler)
    print(f'🍳 Multi-user Recipe Book server running on http://{HOST}:{PORT}')
    print(f'📝 Sign up at http://localhost:{PORT}/signup')
    server.serve_forever()
