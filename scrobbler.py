import logging
import time
import requests
import hashlib
from datetime import datetime, timedelta
import json
import os
import webbrowser
import urllib.parse

# Setup basic logging to show date, level and message
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Last.fm API settings
API_KEY = ""
API_SECRET = ""
API_URL = "http://ws.audioscrobbler.com/2.0/"
CREDENTIALS_FILE = "credentials.json"

class LastFMScrobbler:
    def __init__(self):
        self.session_key = self.load_session()
        
    def load_session(self):
        # Try to load saved session key
        try:
            if os.path.exists(CREDENTIALS_FILE):
                with open(CREDENTIALS_FILE, 'r') as f:
                    data = json.load(f)
                    if 'session_key' in data:
                        return data['session_key']
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
        return None

    def save_credentials(self, session_key):
        # Save session key to file
        try:
            with open(CREDENTIALS_FILE, 'w') as f:
                json.dump({'session_key': session_key}, f)
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")

    def get_token(self):
        # Get new token from Last.fm
        params = {
            'method': 'auth.getToken',
            'api_key': API_KEY,
            'format': 'json'
        }
        response = requests.get(API_URL, params=params)
        data = response.json()
        if 'token' in data:
            return data['token']
        else:
            raise Exception("Failed to get authentication token")

    def authorize_token(self, token):
        # Open browser for user to login to Last.fm
        auth_url = f"http://www.last.fm/api/auth/?api_key={API_KEY}&token={token}"
        print("Please authorize this application by visiting this URL:")
        print(auth_url)
        webbrowser.open(auth_url)
        input("Press Enter after you've authorized the application...")

    def get_session(self, token):
        # Get session key after user authorization
        params = {
            'method': 'auth.getSession',
            'api_key': API_KEY,
            'token': token
        }
        params['api_sig'] = self.get_signature(params)
        params['format'] = 'json'
        response = requests.get(API_URL, params=params)
        data = response.json()
        if 'session' in data:
            session_key = data['session']['key']
            self.save_credentials(session_key)
            return session_key
        else:
            raise Exception("Failed to get session key")

    def ensure_auth(self):
        # Check if logged in, if not, start login process
        if not self.session_key:
            token = self.get_token()
            self.authorize_token(token)
            self.session_key = self.get_session(token)
            print("Successfully authenticated!")

    def get_signature(self, params):
        # Create signature for Last.fm API
        params = params.copy()
        params.pop('format', None)
        
        signature = ''.join([f"{k}{params[k]}" for k in sorted(params.keys())])
        signature += API_SECRET
        
        return hashlib.md5(signature.encode('utf-8')).hexdigest()
    
    def scrobble_track(self, artist, title, timestamp=None):
        # Submit one song to Last.fm
        self.ensure_auth()
        
        params = {
            'method': 'track.scrobble',
            'api_key': API_KEY,
            'sk': self.session_key,
            'artist': artist,
            'track': title,
            'timestamp': str(timestamp or int(time.time()))
        }
        
        params['api_sig'] = self.get_signature(params)
        params['format'] = 'json'
        
        response = requests.post(API_URL, data=params)
        return response.json()
    
    def scrobble_tracks(self, scrobbles):
        # Submit multiple songs at once
        self.ensure_auth()
        
        params = {
            'method': 'track.scrobble',
            'api_key': API_KEY,
            'sk': self.session_key,
        }
        
        # Add each song to the request
        for idx, scrobble in enumerate(scrobbles):
            params[f'artist[{idx}]'] = scrobble['artist']
            params[f'track[{idx}]'] = scrobble['track']
            params[f'timestamp[{idx}]'] = str(scrobble['timestamp'])
        
        params['api_sig'] = self.get_signature(params)
        params['format'] = 'json'
        
        response = requests.post(API_URL, data=params)
        response.raise_for_status()
        return response.json()

    def batch_scrobble(self, artist, title, count, start_date=None):
        # Submit many copies of the same song
        if start_date:
            base_timestamp = int(start_date.timestamp())
        else:
            base_timestamp = int(time.time())
        
        # Set times for each song (3 min apart)
        track_duration = 180
        timestamps = [base_timestamp - (i * track_duration) for i in range(count)]
        timestamps.sort()
        
        # Prepare list of songs
        scrobbles = [{'artist': artist, 'track': title, 'timestamp': ts} for ts in timestamps]
        
        # Send songs in groups of 50
        batch_size = 50
        success_count = 0
        
        for i in range(0, len(scrobbles), batch_size):
            batch = scrobbles[i:i + batch_size]
            try:
                result = self.scrobble_tracks(batch)
                accepted = result.get('scrobbles', {}).get('@attr', {}).get('accepted', 0)
                success_count += int(accepted)
                logger.info(f"Scrobbled {success_count}/{count} tracks")
            except Exception as e:
                logger.error(f"Batch failed: {e}")
            time.sleep(1)  # Wait 1 second between batches
        
        return success_count

def main():
    # Main program loop
    scrobbler = LastFMScrobbler()
    
    try:
        while True:
            print("\n=== Last.fm Scrobbler ===")
            artist = input("Artist name (or 'quit' to exit): ")
            if artist.lower() == 'quit':
                break
            
            title = input("Track title: ")
            count = int(input("Number of scrobbles (max 1000): "))
            count = min(1000, max(1, count))
            
            backdate = input("Backdate scrobbles? (y/n): ").lower() == 'y'
            if backdate:
                days_ago = int(input("How many days ago to start from? "))
                start_date = datetime.now() - timedelta(days=days_ago)
            else:
                start_date = None
            
            print(f"\nScrobbling {count} times...")
            success_count = scrobbler.batch_scrobble(artist, title, count, start_date)
            print(f"\nSuccessfully scrobbled {success_count} times!")
    
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
