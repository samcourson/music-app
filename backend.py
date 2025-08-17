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
        
    def decline_friend_request(self, request_id):
        """Decline a friend request"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM friendships WHERE id = ?", (request_id,))
            conn.commit()
            conn.close()
            return True, "Friend request declined!"
        except Exception as e:
            return False, f"Error: {str(e)}"
        
    def get_friends(self):
        """Get a list of the current user's friends"""
        if not self.current_user:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username
            FROM users u
            JOIN friendships f ON (
                (f.user_id = ? AND f.friend_id = u.id) OR
                (f.friend_id = ? AND f.user_id = u.id)
            )
            WHERE f.status = 'accepted' AND u.id != ?
        """, (self.current_user["id"], self.current_user["id"], self.current_user["id"]))
        friends = cursor.fetchall()
        conn.close()
        return friends