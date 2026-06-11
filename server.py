#!/usr/bin/env python3
import json
import os
import secrets
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime
from bs4 import BeautifulSoup
import requests

SHARED_FILE = 'shared_recipes.json'

def load_shared():
    if os.path.exists(SHARED_FILE):
        with open(SHARED_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_shared(shared):
    with open(SHARED_FILE, 'w') as f:
        json.dump(shared, f, indent=2)

def extract_recipe(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')

    # Try JSON-LD first
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'Recipe':
                        data = item
                        break
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
                for inst in (data.get('recipeInstructions', []) or []):
                    if isinstance(inst, str):
                        instructions.append(inst)
                    elif isinstance(inst, dict):
                        text = inst.get('text', '') or inst.get('name', '')
                        if text:
                            instructions.append(text)
                if ingredients and instructions:
                    return {
                        'title': data.get('name', 'Untitled Recipe'),
                        'ingredients': [i for i in ingredients if i],
                        'instructions': [i for i in instructions if i]
                    }
        except:
            continue

    # Fallback HTML parsing
    title = 'Untitled Recipe'
    for sel in ['h1.recipe-title', 'h1.headline', 'h1']:
        el = soup.select_one(sel)
        if el:
            title = el.get_text().strip()
            break

    ingredients, instructions = [], []
    for sel in ['.recipe-ingredients li', '.ingredients li', '[itemprop="recipeIngredient"]']:
        items = soup.select(sel)
        if items:
            ingredients = [i.get_text().strip() for i in items if i.get_text().strip()]
            break

    for sel in ['.recipe-instructions li', '.instructions li', 'ol li']:
        items = soup.select(sel)
        if items and len(items) > 2:
            instructions = [i.get_text().strip() for i in items if i.get_text().strip()]
            break

    return {'title': title, 'ingredients': ingredients[:30], 'instructions': instructions[:20]}


def send_json(handler, code, data):
    body = json.dumps(data).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            with open('index.html', 'rb') as f:
                self.wfile.write(f.read())

        elif path == '/manifest.json':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with open('manifest.json', 'rb') as f:
                self.wfile.write(f.read())

        elif path == '/service-worker.js':
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript')
            self.end_headers()
            with open('service-worker.js', 'rb') as f:
                self.wfile.write(f.read())

        elif path == '/icon-512.png':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            with open('icon-512.png', 'rb') as f:
                self.wfile.write(f.read())

        elif path.startswith('/shared-json/'):
            share_id = path.split('/')[-1]
            shared = load_shared()
            if share_id not in shared:
                self.send_response(404)
                self.end_headers()
                return
            send_json(self, 200, shared[share_id]['recipe'])

        elif path.startswith('/shared/'):
            share_id = path.split('/')[-1]
            shared = load_shared()
            if share_id not in shared:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'<h1>Recipe not found</h1>')
                return
            recipe = shared[share_id]['recipe']
            html = get_shared_html(recipe, share_id)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        data = json.loads(self.rfile.read(length)) if length else {}

        if path == '/api/scrape':
            url = data.get('url', '')
            try:
                recipe = extract_recipe(url)
                if not recipe.get('ingredients') or not recipe.get('instructions') or len(recipe['ingredients']) < 2:
                    send_json(self, 400, {'error': 'Could not extract recipe from this site.', 'blocked': True})
                    return
                send_json(self, 200, recipe)
            except Exception as e:
                err = str(e)
                blocked = any(c in err for c in ['402', '403', 'Forbidden', 'Payment'])
                send_json(self, 400, {'error': err, 'blocked': blocked})

        elif path == '/api/share':
            recipe = data.get('recipe')
            if not recipe:
                send_json(self, 400, {'error': 'No recipe provided'})
                return
            share_id = secrets.token_urlsafe(16)
            shared = load_shared()
            shared[share_id] = {'recipe': recipe, 'created': datetime.now().isoformat()}
            save_shared(shared)
            send_json(self, 200, {'shareId': share_id})

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def get_shared_html(recipe, share_id):
    title = recipe['title']
    category = recipe.get('category', 'Other')
    notes = recipe.get('notes', '')
    ingredients_html = '<ul>' + ''.join(f'<li>{i}</li>' for i in recipe.get('ingredients', [])) + '</ul>'
    instructions_html = '<ol>' + ''.join(f'<li>{i}</li>' for i in recipe.get('instructions', [])) + '</ol>'

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Recipe Book</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: Georgia, serif; background: #f9f7f4; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .top-bar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }}
        .brand {{ color:#2d5016; font-size:22px; text-decoration:none; font-weight:bold; }}
        .recipe {{ background:white; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); padding:30px; }}
        h1 {{ color:#2d5016; font-size:28px; margin-bottom:8px; }}
        .category {{ color:#888; margin-bottom:20px; }}
        h2 {{ color:#2d5016; font-size:20px; margin:25px 0 12px; border-bottom:2px solid #f4d03f; padding-bottom:6px; }}
        ul,ol {{ margin-left:22px; }} li {{ padding:7px 0; line-height:1.6; }}
        .notes {{ margin-top:25px; padding:15px; background:#fff9e6; border-radius:4px; border-left:4px solid #f4d03f; }}
        .actions {{ margin:20px 0; display:flex; gap:10px; flex-wrap:wrap; }}
        .btn {{ padding:12px 24px; border:none; border-radius:4px; cursor:pointer; font-size:16px; font-weight:bold; text-decoration:none; display:inline-block; }}
        .btn-save {{ background:#2d5016; color:white; }}
        .btn-print {{ background:#f4d03f; color:#333; }}
        @media print {{ .actions,.top-bar {{ display:none; }} body {{ background:white; padding:0; }} .recipe {{ box-shadow:none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="top-bar"><a href="/" class="brand">🍳 Recipe Book</a></div>
        <div class="actions">
            <a href="/?import={share_id}" class="btn btn-save">➕ Save to My Recipe Book</a>
            <button class="btn btn-print" onclick="window.print()">🖨️ Print</button>
        </div>
        <div class="recipe">
            <h1>{title}</h1>
            <p class="category">{category}</p>
            <h2>Ingredients</h2>{ingredients_html}
            <h2>Instructions</h2>{instructions_html}
            {f'<div class="notes"><strong>Notes:</strong><br><br>{notes}</div>' if notes else ''}
        </div>
    </div>
</body>
</html>'''


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    print(f'🍳 Recipe Book server running on http://0.0.0.0:{PORT}')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
