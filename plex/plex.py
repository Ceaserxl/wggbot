from flask import Flask, render_template, jsonify, redirect, request, url_for
import requests
import xmltodict
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

#PLEX_TOKEN = os.getenv('PLEX_TOKEN')
#PLEX_URL = os.getenv('PLEX_URL')
PLEX_URL = "http://185.162.184.38:6088"
PLEX_TOKEN = "6yZcn_sZoXKcQWy4s4sf"
# Cache for movies
movie_cache = {
    'data': None,
    'timestamp': 0
}

def get_plex_data(endpoint):
    headers = {
        'X-Plex-Token': PLEX_TOKEN
    }
    response = requests.get(f'{PLEX_URL}{endpoint}', headers=headers)
    if response.status_code == 200:
        try:
            data = xmltodict.parse(response.content)
            return data
        except Exception as e:
            print(f'XML Parse Error: {e}')
            return None  # Invalid XML
    else:
        return None  # Non-200 status code

def get_cached_movies():
    current_time = time.time()
    cache_age_minutes = (current_time - movie_cache['timestamp']) / 60
    # Check if the cache is older than 5 minutes (300 seconds)
    if current_time - movie_cache['timestamp'] > 300:
        print("Cache is older than 5 minutes, fetching new data.")
        data = get_plex_data('/library/sections/1/all')  # Assuming '1' is the section ID for Movies
        if data:
            movie_cache['data'] = data
            movie_cache['timestamp'] = current_time
            print("Fetched new data and updated the cache.")
    else:
        print(f"Cache is only {cache_age_minutes:.2f} minutes old, using cache.")
    return movie_cache['data']

@app.route('/')
def index():
    user_ip = request.remote_addr
    print(f'Page loaded by user with IP: {user_ip}')
    return render_template('index.html')

@app.route('/library')
def library():
    data = get_cached_movies()
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Failed to fetch data from Plex server'}), 500

@app.route('/library/section/<int:section_id>')
def library_section(section_id):
    if section_id == 1:
        data = get_cached_movies()
    else:
        data = get_plex_data(f'/library/sections/{section_id}/all')
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': f'Failed to fetch section {section_id} data from Plex server'}), 500

@app.route('/watch/<int:movie_id>')
def watch_movie(movie_id):
    user_ip = request.remote_addr
    data = get_plex_data(f'/library/metadata/{movie_id}')
    if data:
        media_container = data.get('MediaContainer', {})
        metadata = media_container.get('Video', {})
        if metadata:
            movie_title = metadata.get('@title')
            media = metadata.get('Media', {})
            if media:
                part = media.get('Part', {})
                if part:
                    stream_url = part.get('@key')
                    if stream_url:
                        print(f'User with IP: {user_ip} clicked "Watch" on movie: {movie_title}')
                        # Redirect to an intermediate route
                        return redirect(url_for('play_movie', movie_id=movie_id, title=movie_title))
    print(f'Failed to fetch movie {movie_id} data for user with IP: {user_ip}')
    return jsonify({'error': f'Failed to fetch movie {movie_id} data from Plex server'}), 500

@app.route('/play/<int:movie_id>')
def play_movie(movie_id):
    title = request.args.get('title')
    data = get_plex_data(f'/library/metadata/{movie_id}')
    if data:
        media_container = data.get('MediaContainer', {})
        metadata = media_container.get('Video', {})
        if metadata:
            media = metadata.get('Media', {})
            if media:
                part = media.get('Part', {})
                if part:
                    stream_url = part.get('@key')
                    if stream_url:
                        # The actual stream URL to be played by the client
                        play_url = f'{PLEX_URL}{stream_url}?X-Plex-Token={PLEX_TOKEN}'
                        return render_template('play.html', play_url=play_url, title=title)
    return 'Stream URL or title is missing', 400

@app.route('/catalog.html')
def catalog():
    user_ip = request.remote_addr
    print(f'Page loaded by user with IP: {user_ip}')
    return render_template('catalog.html', plex_token=PLEX_TOKEN, plex_url=PLEX_URL)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False, port=80)
