from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
import os
from dotenv import load_dotenv
from backend import SongInstagramApp
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Initialize the backend app
backend_app = SongInstagramApp()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('feed'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        success, message = backend_app.login_user(username, password)
        
        if success:
            session['user_id'] = backend_app.current_user
            session['username'] = username
            flash('Successfully logged in!', 'success')
            return redirect(url_for('feed'))
        else:
            flash(message, 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        # email = request.form['email']
        email = '' # Temporarily disabled email registration
        password = request.form['password']
        success, message = backend_app.register_user(username, email, password)
        
        if success:
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out!', 'success')
    return redirect(url_for('login'))

@app.route('/feed')
@login_required
def feed():
    posts = backend_app.get_feed()
    return render_template('feed.html', posts=posts, username=session.get('username'))

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        song_title = request.form['song_title']
        artist = request.form['artist']
        album = request.form['album']
        cover_url = request.form['cover_url']
        caption = request.form['caption']
        spotify_url = request.form.get('spotify_url', '')
        apple_music_url = request.form.get('apple_music_url', '')
        
        success, message = backend_app.create_post(
            song_title, artist, album, cover_url, 
            spotify_url, apple_music_url, caption
        )
        
        if success:
            flash('Post created successfully!', 'success')
            return redirect(url_for('feed'))
        else:
            flash(message, 'error')
    
    return render_template('create_post.html', username=session.get('username'))

@app.route('/friends')
@login_required
def friends():
    friend_requests = backend_app.get_friend_requests()
    return render_template('friends.html', 
                         friend_requests=friend_requests, 
                         username=session.get('username'))

@app.route('/profile')
@login_required
def profile():
    # Get user's own posts
    user_posts = backend_app.get_user_posts(session['user_id']) if hasattr(backend_app, 'get_user_posts') else []
    return render_template('profile.html', 
                         posts=user_posts, 
                         username=session.get('username'))

# API Routes for AJAX interactions
@app.route('/api/search_songs')
@login_required
def search_songs():
    query = request.args.get('query', '')
    if not query.strip():
        return jsonify([])
    
    results = backend_app.search_song_spotify(query)
    return jsonify(results)

@app.route('/api/search_users')
@login_required
def search_users():
    query = request.args.get('query', '')
    if not query.strip():
        return jsonify([])
    
    users = backend_app.search_users(query)
    return jsonify([{'id': user[0], 'username': user[1]} for user in users])

@app.route('/api/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    success, message = backend_app.like_post(post_id)
    return jsonify({'success': success, 'message': message})

@app.route('/api/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    comment_text = request.json.get('comment', '')
    if not comment_text.strip():
        return jsonify({'success': False, 'message': 'Comment cannot be empty'})
    
    success, message = backend_app.add_comment(post_id, comment_text.strip())
    return jsonify({'success': success, 'message': message})

@app.route('/api/get_comments/<int:post_id>')
@login_required
def get_comments(post_id):
    comments = backend_app.get_comments(post_id)
    return jsonify([{
        'comment': comment[0],
        'username': comment[1],
        'created_at': comment[2]
    } for comment in comments])

@app.route('/api/send_friend_request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    success, message = backend_app.send_friend_request(user_id)
    return jsonify({'success': success, 'message': message})

@app.route('/api/get_friends')
@login_required
def get_friends():
    friends = backend_app.get_friends()
    return jsonify([{'id': friend[0], 'username': friend[1]} for friend in friends])

@app.route('/api/handle_friend_request/<int:user_id>', methods=['POST'])
@login_required
def handle_friend_request(user_id):
    data = request.json
    action = data.get('action', '')

    if action not in ['accept', 'decline']:
        return jsonify({'success': False, 'message': 'Invalid action.'})

    if action == 'accept':
        success, message = backend_app.accept_friend_request(user_id)
    else:
        success, message = backend_app.decline_friend_request(user_id)

    return jsonify({'success': success, 'user_id': user_id, 'message': message})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)