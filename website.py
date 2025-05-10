import os
import json
import requests
import logging
from flask import Flask, render_template, jsonify
from resources import keys

# Initialize Flask app
app = Flask(__name__, template_folder='resources/templates')

# Configure logging
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# Environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', keys.DISCORD_TOKEN)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', keys.OPENAI_API_KEY)
CONVERSATION_HISTORY_FILE = 'resources/jsons/conversation_history.json'

# Persistent username cache file
CACHE_FILE = 'resources/jsons/user_cache.json'
try:
    with open(CACHE_FILE, 'r') as f:
        username_cache = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    username_cache = {}

# Resolve user ID to username with file-based caching and retry for Unknown User
def get_username(user_id):
    # Return cached username if known and not 'Unknown User'
    cached = username_cache.get(user_id)
    if cached and cached != 'Unknown User':
        return cached

    # Fetch from Discord API
    headers = {'Authorization': f'Bot {DISCORD_TOKEN}'}
    try:
        response = requests.get(f'https://discord.com/api/v9/users/{user_id}', headers=headers)
        response.raise_for_status()
        username = response.json().get('username', 'Unknown User')
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to fetch user {user_id}: {e}")
        username = 'Unknown User'

    # Cache only real usernames (retry on 'Unknown User' next time)
    if username != 'Unknown User':
        username_cache[user_id] = username
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(username_cache, f)
        except Exception as e:
            app.logger.error(f"Failed to write cache file: {e}")

    return username

# Load conversation history from disk
def load_conversation_history():
    try:
        with open(CONVERSATION_HISTORY_FILE, 'r') as file:
            return json.load(file)
    except Exception as e:
        app.logger.error(f"Error loading conversation history: {e}")
        raise

# Jinja filter to detect image URLs
@app.template_filter('is_image_url')
def is_image_url_filter(s):
    return s.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))

# Web routes
@app.route('/')
def index():
    try:
        conversation_history = load_conversation_history()
        resolved_history = {}
        for user_id, messages in conversation_history.items():
            username = get_username(user_id)
            resolved_history[username] = messages
        return render_template('index.html', conversation_history=resolved_history)
    except Exception as e:
        app.logger.error(f"Error in index route: {e}")
        return f"An error occurred: {e}"

@app.route('/api/conversations')
def api_conversations():
    try:
        conversation_history = load_conversation_history()
        resolved_history = {}
        for user_id, messages in conversation_history.items():
            username = get_username(user_id)
            resolved_history[username] = messages
        return jsonify(resolved_history)
    except Exception as e:
        app.logger.error(f"Error in api_conversations route: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# Run the app
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=80)
