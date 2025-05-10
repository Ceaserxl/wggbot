from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_socketio import SocketIO, join_room, leave_room, emit, disconnect
import hashlib
from urllib.parse import urlparse, unquote
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Dictionary to store the state of each room
rooms = {}
# Dictionary to store the last heartbeat time for each viewer
viewers = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create():
    video_url = request.form['video_url']
    room_id = hashlib.md5(video_url.encode()).hexdigest()
    movie_name = unquote(urlparse(video_url).path.split('/')[-1]).replace('%20', ' ')  # Extract and decode the file name from the URL
    rooms[room_id] = {'video_url': video_url, 'currentTime': 0, 'playing': False, 'viewers': 0}
    return redirect(url_for('room', room_id=room_id))

@app.route('/room/<room_id>')
def room(room_id):
    if room_id in rooms:
        video_url = rooms[room_id]['video_url']
        movie_name = unquote(urlparse(video_url).path.split('/')[-1]).replace('%20', ' ')
        return render_template('room.html', room_id=room_id, video_url=video_url, movie_name=movie_name)
    return redirect(url_for('home'))

@app.route('/get_furthest_time/<room_id>')
def get_furthest_time(room_id):
    if room_id in rooms:
        return jsonify({'currentTime': rooms[room_id]['currentTime'], 'playing': rooms[room_id]['playing']})
    return jsonify({'currentTime': 0, 'playing': False})

@socketio.on('join')
def on_join(data):
    room = data['room']
    viewer_id = request.sid
    join_room(room)
    rooms[room]['viewers'] += 1
    viewers[viewer_id] = {'room': room, 'last_heartbeat': time.time()}
    emit('status', {'msg': 'A user has entered the room.'}, to=room)
    emit('viewers', {'count': rooms[room]['viewers']}, to=room)
    # Emit the current state to the new user
    emit('sync', {'currentTime': rooms[room]['currentTime'], 'playing': rooms[room]['playing']}, to=room)

@socketio.on('leave')
def on_leave():
    viewer_id = request.sid
    if viewer_id in viewers:
        room = viewers[viewer_id]['room']
        rooms[room]['viewers'] -= 1
        del viewers[viewer_id]
        emit('status', {'msg': 'A user has left the room.'}, to=room)
        emit('viewers', {'count': rooms[room]['viewers']}, to=room)

@socketio.on('play')
def on_play(data):
    room = data['room']
    rooms[room]['playing'] = True
    emit('play', {}, to=room)

@socketio.on('pause')
def on_pause(data):
    room = data['room']
    rooms[room]['playing'] = False
    emit('pause', {}, to=room)

@socketio.on('sync')
def on_sync(data):
    room = data['room']
    currentTime = data['currentTime']
    if currentTime > rooms[room]['currentTime']:
        rooms[room]['currentTime'] = currentTime
    emit('sync', {'currentTime': rooms[room]['currentTime'], 'playing': rooms[room]['playing']}, to=room)

@socketio.on('heartbeat')
def on_heartbeat():
    viewer_id = request.sid
    if viewer_id in viewers:
        viewers[viewer_id]['last_heartbeat'] = time.time()

def check_viewers():
    while True:
        current_time = time.time()
        timeout = 30  # Timeout in seconds
        for viewer_id in list(viewers):
            if current_time - viewers[viewer_id]['last_heartbeat'] > timeout:
                room = viewers[viewer_id]['room']
                rooms[room]['viewers'] -= 1
                del viewers[viewer_id]
                socketio.emit('viewers', {'count': rooms[room]['viewers']}, to=room)
                socketio.emit('status', {'msg': 'A user has been disconnected due to inactivity.'}, to=room)
                disconnect(viewer_id)
        socketio.sleep(10)

if __name__ == '__main__':
    socketio.start_background_task(target=check_viewers)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
