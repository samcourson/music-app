import gradio as gr
import sqlite3
import json
import requests
from datetime import datetime, timedelta
import base64
import io
from PIL import Image
import os
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

class SpotifyAPI:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires = None
        self.base_url = "https://api.spotify.com/v1"
    
    def get_access_token(self):
        """Get access token using Client Credentials flow"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        
        # Encode client credentials
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        # Request token
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "client_credentials"
        }
        
        try:
            response = requests.post("https://accounts.spotify.com/api/token", 
                                   headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            # Set expiration time (subtract 5 minutes for safety)
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires = datetime.now() + timedelta(seconds=expires_in - 300)
            
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"Error getting access token: {e}")
            return None
    
    def search_song_spotify(self, query, limit=10):
        """Search for songs using Spotify Web API"""
        if not query.strip():
            return []
        
        access_token = self.get_access_token()
        if not access_token:
            print("Failed to get access token")
            return self._get_fallback_results(query)
        
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        params = {
            "q": query,
            "type": "track",
            "limit": limit,
            "market": "US"  # You can change this or make it configurable
        }
        
        try:
            response = requests.get(f"{self.base_url}/search", 
                                  headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            tracks = data.get("tracks", {}).get("items", [])
            
            results = []
            for track in tracks:
                # Get the largest image (usually 640x640)
                image_url = ""
                if track["album"]["images"]:
                    image_url = track["album"]["images"][0]["url"]
                
                # Build Apple Music search URL (since we don't have Apple Music API access)
                apple_music_url = self._build_apple_music_url(track["name"], 
                                                            track["artists"][0]["name"])
                
                result = {
                    "name": track["name"],
                    "artist": ", ".join([artist["name"] for artist in track["artists"]]),
                    "album": track["album"]["name"],
                    "image": image_url,
                    "spotify_url": track["external_urls"]["spotify"],
                    "apple_music_url": apple_music_url,
                    "preview_url": track.get("preview_url"),  # 30-second preview
                    "duration_ms": track["duration_ms"],
                    "popularity": track["popularity"],
                    "explicit": track["explicit"]
                }
                results.append(result)
            
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching Spotify: {e}")
            return self._get_fallback_results(query)
        except (KeyError, ValueError) as e:
            print(f"Error parsing Spotify response: {e}")
            return self._get_fallback_results(query)
    
    def _build_apple_music_url(self, song_name, artist_name):
        """Build Apple Music search URL"""
        search_term = f"{song_name} {artist_name}".replace(" ", "+")
        return f"https://music.apple.com/search?term={search_term}"

class SongInstagramApp:
    def __init__(self, db_path="song_instagram.db"):
        self.db_path = db_path
        self.current_user = None
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Posts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                song_title TEXT NOT NULL,
                artist TEXT NOT NULL,
                album TEXT,
                album_cover_url TEXT,
                spotify_url TEXT,
                apple_music_url TEXT,
                caption TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Friendships table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friendships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (friend_id) REFERENCES users (id),
                UNIQUE(user_id, friend_id)
            )
        """)
        
        # Likes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (post_id) REFERENCES posts (id),
                UNIQUE(user_id, post_id)
            )
        """)
        
        # Comments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                comment TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def register_user(self, username, email, password):
        """Register a new user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                         (username, email, password))
            conn.commit()
            conn.close()
            return True, "User registered successfully!"
        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                return False, "Username already exists!"
            elif "email" in str(e):
                return False, "Email already exists!"
            return False, "Registration failed!"
    
    def login_user(self, username, password):
        """Login user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE username = ? AND password = ?",
                      (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            self.current_user = {"id": user[0], "username": user[1]}
            return True, f"Welcome back, {username}!"
        return False, "Invalid username or password!"
    
    def search_song_spotify(self, query):
        """Search for a song using Spotify Web API"""
        
        spotify_api = SpotifyAPI(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        results = spotify_api.search_song_spotify(query)

        return results if results else []
    
    def create_post(self, song_title, artist, album, album_cover_url, spotify_url, apple_music_url, caption):
        """Create a new post"""
        if not self.current_user:
            return False, "Please login first!"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO posts (user_id, song_title, artist, album, album_cover_url, 
                                 spotify_url, apple_music_url, caption)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (self.current_user["id"], song_title, artist, album, album_cover_url, 
                  spotify_url, apple_music_url, caption))
            conn.commit()
            conn.close()
            return True, "Post created successfully!"
        except Exception as e:
            return False, f"Error creating post: {str(e)}"
        
    def delete_post(self, post_id):
        """Delete a post created by the current user"""
        if not self.current_user:
            return False, "Please login first!"
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Ensure the post belongs to the current user
            cursor.execute("SELECT id FROM posts WHERE id = ? AND user_id = ?", (post_id, self.current_user["id"]))
            post = cursor.fetchone()
            if not post:
                conn.close()
                return False, "You can only delete your own posts!"
            # Delete likes and comments associated with the post
            cursor.execute("DELETE FROM likes WHERE post_id = ?", (post_id,))
            cursor.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
            # Delete the post itself
            cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            conn.commit()
            conn.close()
            return True, "Post deleted successfully!"
        except Exception as e:
            return False, f"Error deleting post: {str(e)}"
    
    def get_feed(self):
        """Get posts for the current user's feed"""
        if not self.current_user:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get posts from user and friends
        cursor.execute("""
            SELECT p.id, p.song_title, p.artist, p.album, p.album_cover_url,
                   p.spotify_url, p.apple_music_url, p.caption, p.created_at,
                   u.username,
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as like_count,
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id AND user_id = ?) as user_liked
            FROM posts p
            JOIN users u ON p.user_id = u.id
            LEFT JOIN friendships f ON (f.user_id = ? AND f.friend_id = p.user_id AND f.status = 'accepted')
            WHERE p.user_id = ? OR f.friend_id IS NOT NULL
            ORDER BY p.created_at DESC
        """, (self.current_user["id"], self.current_user["id"], self.current_user["id"]))
        
        posts = cursor.fetchall()
        conn.close()
        return posts
    
    def like_post(self, post_id):
        """Like/unlike a post"""
        if not self.current_user:
            return False, "Please login first!"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if already liked
            cursor.execute("SELECT id FROM likes WHERE user_id = ? AND post_id = ?",
                          (self.current_user["id"], post_id))
            existing_like = cursor.fetchone()
            
            if existing_like:
                # Unlike
                cursor.execute("DELETE FROM likes WHERE user_id = ? AND post_id = ?",
                              (self.current_user["id"], post_id))
                message = "Post unliked!"
            else:
                # Like
                cursor.execute("INSERT INTO likes (user_id, post_id) VALUES (?, ?)",
                              (self.current_user["id"], post_id))
                message = "Post liked!"
            
            conn.commit()
            conn.close()
            return True, message
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def add_comment(self, post_id, comment):
        """Add a comment to a post"""
        if not self.current_user:
            return False, "Please login first!"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO comments (user_id, post_id, comment) VALUES (?, ?, ?)",
                          (self.current_user["id"], post_id, comment))
            conn.commit()
            conn.close()
            return True, "Comment added!"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def get_comments(self, post_id):
        """Get comments for a post"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.comment, u.username, c.created_at
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = ?
            ORDER BY c.created_at ASC
        """, (post_id,))
        comments = cursor.fetchall()
        conn.close()
        return comments
    
    def search_users(self, query):
        """Search for users"""
        if not self.current_user:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username FROM users 
            WHERE username LIKE ? AND id != ?
        """, (f"%{query}%", self.current_user["id"]))
        users = cursor.fetchall()
        conn.close()
        return users
    
    def send_friend_request(self, friend_id):
        """Send a friend request"""
        if not self.current_user:
            return False, "Please login first!"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO friendships (user_id, friend_id) VALUES (?, ?)",
                          (self.current_user["id"], friend_id))
            conn.commit()
            conn.close()
            return True, "Friend request sent!"
        except sqlite3.IntegrityError:
            return False, "Friend request already sent or you're already friends!"
    
    def get_friend_requests(self):
        """Get pending friend requests"""
        if not self.current_user:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f.id, u.username FROM friendships f
            JOIN users u ON f.user_id = u.id
            WHERE f.friend_id = ? AND f.status = 'pending'
        """, (self.current_user["id"],))
        requests = cursor.fetchall()
        conn.close()
        return requests
    
    def accept_friend_request(self, request_id):
        """Accept a friend request"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE friendships SET status = 'accepted' WHERE id = ?", (request_id,))
            conn.commit()
            conn.close()
            return True, "Friend request accepted!"
        except Exception as e:
            return False, f"Error: {str(e)}"

# Initialize the app
app = SongInstagramApp()

def create_gradio_interface():
    with gr.Blocks(title="Song Instagram", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🎵 Song Instagram")
        gr.Markdown("Share your favorite songs with friends!")
        
        # User state
        user_state = gr.State(None)
        
        with gr.Tabs() as tabs:
            # Authentication Tab
            with gr.Tab("🔐 Login/Register"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Login")
                        login_username = gr.Textbox(label="Username")
                        login_password = gr.Textbox(label="Password", type="password")
                        login_btn = gr.Button("Login", variant="primary")
                        login_status = gr.Textbox(label="Status", interactive=False)
                    
                    with gr.Column():
                        gr.Markdown("### Register")
                        reg_username = gr.Textbox(label="Username")
                        reg_email = gr.Textbox(label="Email")
                        reg_password = gr.Textbox(label="Password", type="password")
                        register_btn = gr.Button("Register", variant="secondary")
                        register_status = gr.Textbox(label="Status", interactive=False)
            
            # Create Post Tab
            with gr.Tab("➕ Create Post"):
                current_user_display = gr.Markdown("**Not logged in**")
                
                with gr.Row():
                    search_query = gr.Textbox(label="Search for a song", placeholder="Enter song name or artist")
                    search_btn = gr.Button("Search")
                
                song_results = gr.Radio(label="Select a song", choices=[], interactive=True)
                
                with gr.Row():
                    selected_song_title = gr.Textbox(label="Song Title", interactive=False)
                    selected_artist = gr.Textbox(label="Artist", interactive=False)
                
                with gr.Row():
                    selected_album = gr.Textbox(label="Album", interactive=False)
                    selected_cover_url = gr.Textbox(label="Cover URL", interactive=False)
                    selected_spotify_url = gr.Textbox(label="Spotify URL", interactive=False)
                    selected_apple_music_url = gr.Textbox(label="Apple Music URL", interactive=False)
                
                post_caption = gr.Textbox(label="Caption", placeholder="What do you think about this song?")
                create_post_btn = gr.Button("Create Post", variant="primary")
                post_status = gr.Textbox(label="Status", interactive=False)
            
            # Feed Tab
            with gr.Tab("🏠 Feed"):
                refresh_feed_btn = gr.Button("Refresh Feed")
                feed_display = gr.HTML()
                with gr.Row():
                    delete_post_id = gr.Number(label="Post ID to delete", precision=0)
                    delete_post_btn = gr.Button("Delete Post", variant="stop")
                    delete_post_status = gr.Textbox(label="Delete Status", interactive=False)
            
            # Friends Tab
            with gr.Tab("👥 Friends"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Find Friends")
                        user_search = gr.Textbox(label="Search users", placeholder="Enter username")
                        search_users_btn = gr.Button("Search")
                        user_results = gr.Radio(label="Users", choices=[])
                        send_request_btn = gr.Button("Send Friend Request")
                        friend_status = gr.Textbox(label="Status", interactive=False)
                    
                    with gr.Column():
                        gr.Markdown("### Friend Requests")
                        refresh_requests_btn = gr.Button("Refresh Requests")
                        friend_requests_radio = gr.Radio(label="Pending Requests", choices=[])
                        accept_request_btn = gr.Button("Accept Friend Request")
                        friend_requests_status = gr.Textbox(label="Status", interactive=False)
        
        # Event handlers
        def handle_login(username, password):
            success, message = app.login_user(username, password)
            if success:
                return message, f"**Logged in as: {username}**"
            return message, "**Not logged in**"
        
        def handle_register(username, email, password):
            success, message = app.register_user(username, email, password)
            return message
        
        def handle_search_songs(query):
            if not query.strip():
                return gr.Radio(choices=[])
            
            results = app.search_song_spotify(query)
            choices = [f"{r['name']} - {r['artist']}" for r in results]
            return gr.Radio(choices=choices, value=None if not choices else choices[0])
        
        def handle_song_selection(selected):
            if not selected:
                return "", "", "", "", "", ""
            
            # Parse the selection
            song_name, artist = selected.split(" - ", 1)
            results = app.search_song_spotify(song_name)
            
            for result in results:
                if result['name'] == song_name and result['artist'] == artist:
                    return result['name'], result['artist'], result['album'], result['image'], result['spotify_url'], result['apple_music_url']
            
            return "", "", "", "", "", ""
        
        def handle_create_post(song_title, artist, album, cover_url, spotify_url, apple_music_url, caption):
            if not all([song_title, artist, album, cover_url]):
                return "Please select a song first!"
            
            spotify_url = spotify_url or f"https://open.spotify.com/search/{song_title}%20{artist}"
            apple_music_url = apple_music_url or f"https://music.apple.com/search?term={song_title}+{artist}"
            
            success, message = app.create_post(song_title, artist, album, cover_url, 
                                             spotify_url, apple_music_url, caption)
            return message
        
        def handle_refresh_feed():
            posts = app.get_feed()
            if not posts:
                return "<p>No posts to show. Follow some friends and start sharing songs!</p>"
            
            html = "<div style='max-width: 600px;'>"
            for post in posts:
                post_id, song_title, artist, album, cover_url, spotify_url, apple_music_url, caption, created_at, username, like_count, user_liked = post
                
                like_emoji = "❤️" if user_liked else "🤍"
                
                html += f"""
                <div style='border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 20px; background: white;'>
                    <div style='display: flex; align-items: center; margin-bottom: 10px;'>
                        <strong>@{username}</strong>
                        <span style='margin-left: auto; color: #666; font-size: 12px;'>{created_at}</span>
                    </div>
                    
                    <div style='display: flex; gap: 15px; margin-bottom: 10px;'>
                        <img src='{cover_url}' style='width: 100px; height: 100px; border-radius: 8px; object-fit: cover;' />
                        <div style='flex: 1;'>
                            <h3 style='margin: 0; font-size: 18px;'>{song_title}</h3>
                            <p style='margin: 5px 0; color: #666;'>by {artist}</p>
                            <p style='margin: 5px 0; color: #888; font-size: 14px;'>{album}</p>
                            <div style='margin-top: 10px;'>
                                <a href='{spotify_url}' target='_blank' style='margin-right: 10px; color: #1DB954; text-decoration: none;'>🎵 Spotify</a>
                                <a href='{apple_music_url}' target='_blank' style='color: #FA243C; text-decoration: none;'>🍎 Apple Music</a>
                            </div>
                        </div>
                    </div>
                    
                    {f"<p style='margin: 10px 0; font-style: italic;'>{caption}</p>" if caption else ""}
                    
                    <div style='border-top: 1px solid #eee; padding-top: 10px; margin-top: 10px;'>
                        <span>{like_emoji} {like_count} likes</span>
                    </div>
                </div>
                """
            
            html += "</div>"
            return html
        
        def handle_delete_post(post_id):
            success, message = app.delete_post(post_id)
            return message

        def handle_search_users(query):
            if not query.strip():
                return gr.Radio(choices=[])
            
            users = app.search_users(query)
            choices = [f"{user[1]} (ID: {user[0]})" for user in users]
            return gr.Radio(choices=choices)
        
        def handle_send_friend_request(selected_user):
            if not selected_user:
                return "Please select a user first!"
            
            # Extract user ID from the selection
            user_id = int(selected_user.split("ID: ")[1].split(")")[0])
            success, message = app.send_friend_request(user_id)
            return message
        
        def handle_refresh_requests():
            requests = app.get_friend_requests()
            if not requests:
                return gr.Radio(choices=[]), "No pending friend requests."
            choices = [f"{username} (Request ID: {req_id})" for req_id, username in requests]
            return gr.Radio(choices=choices), ""

        def handle_accept_friend_request(selected_request):
            if not selected_request:
                return "Please select a request to accept."
            request_id = int(selected_request.split("Request ID: ")[1].split(")")[0])
            success, message = app.accept_friend_request(request_id)
            return message
        
        # Connect event handlers
        login_btn.click(
            handle_login,
            inputs=[login_username, login_password],
            outputs=[login_status, current_user_display]
        )
        
        register_btn.click(
            handle_register,
            inputs=[reg_username, reg_email, reg_password],
            outputs=[register_status]
        )
        
        search_btn.click(
            handle_search_songs,
            inputs=[search_query],
            outputs=[song_results]
        )
        
        song_results.change(
            handle_song_selection,
            inputs=[song_results],
            outputs=[selected_song_title, selected_artist, selected_album, selected_cover_url, selected_spotify_url, selected_apple_music_url]
        )
        
        create_post_btn.click(
            handle_create_post,
            inputs=[selected_song_title, selected_artist, selected_album, selected_cover_url, selected_spotify_url, selected_apple_music_url, post_caption],
            outputs=[post_status]
        )

        delete_post_btn.click(
            handle_delete_post,
            inputs=[delete_post_id],
            outputs=[delete_post_status]
        )
        
        refresh_feed_btn.click(
            handle_refresh_feed,
            outputs=[feed_display]
        )
        
        search_users_btn.click(
            handle_search_users,
            inputs=[user_search],
            outputs=[user_results]
        )
        
        send_request_btn.click(
            handle_send_friend_request,
            inputs=[user_results],
            outputs=[friend_status]
        )
        
        refresh_requests_btn.click(
            handle_refresh_requests,
            outputs=[friend_requests_radio, friend_requests_status]
        )

        accept_request_btn.click(
            handle_accept_friend_request,
            inputs=[friend_requests_radio],
            outputs=[friend_requests_status]
        )
    
    return demo

if __name__ == "__main__":
    demo = create_gradio_interface()
    demo.launch(share=True, debug=True)