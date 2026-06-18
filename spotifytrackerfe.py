import os
import json
import requests
import spotipy
from groq import Groq
from dotenv import load_dotenv

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {"liked": [], "disliked": [], "seen": []}

def save_history(liked, disliked, seen):
    with open(HISTORY_FILE, "w") as f:
        json.dump({"liked": liked, "disliked": disliked, "seen": seen}, f)

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

sp = None

def init_spotify(access_token):
    global sp
    sp = spotipy.Spotify(auth=access_token)

def top_tracks():
    return sp.current_user_top_tracks(limit=10)['items']

def top_artists():
    return sp.current_user_top_artists(limit=10)['items']

def recently_played():
    return sp.current_user_recently_played(limit=10)['items']

def followed_artists():
    return sp.current_user_followed_artists(limit=10)['artists']['items']

def playlists():
    return sp.current_user_playlists(limit=10)['items']

def saved_tracks():
    return sp.current_user_saved_tracks(limit=10)['items']

def build_profile():
    tracks = top_tracks()
    artists = top_artists()
    genres = []
    for a in artists:
        genres.extend(a.get('genres', []))
    recent = recently_played()
    followed = followed_artists()
    user_playlists = playlists()
    saved = saved_tracks()
    return {
        'tracks': ', '.join([t['name'] + " by " + t['artists'][0]['name'] for t in tracks]),
        'artists': ', '.join([a['name'] for a in artists]),
        'genres': ', '.join(list(set(genres))),
        'recent': ', '.join([t['track']['name'] + " by " + t['track']['artists'][0]['name'] for t in recent]),
        'followed': ', '.join([a['name'] for a in followed]),
        'playlists': ', '.join([p['name'] for p in user_playlists]),
        'saved': ', '.join([t['track']['name'] + " by " + t['track']['artists'][0]['name'] for t in saved]),
    }

def get_next_song(profile, liked, disliked, seen, preferences=None):
    seen_set = {s.lower() for s in seen}
    for _ in range(5):
        song = _fetch_song(profile, liked, disliked, seen, preferences)
        if song.lower() not in seen_set:
            return song
    return song

def _fetch_song(profile, liked, disliked, seen, preferences=None):
    liked_str = ', '.join(liked) if liked else 'none'
    disliked_str = ', '.join(disliked) if disliked else 'none'
    seen_str = ', '.join(seen) if seen else 'none'

    pref_block = ""
    if preferences:
        genres = preferences.get('genres', [])
        vibe = preferences.get('vibe') or []
        vibe_str = ', '.join(vibe) if isinstance(vibe, list) else (vibe or 'any')
        genre_str = ', '.join(genres) if genres else 'none specified'
        genre_rule = f"STRICT RULE: Only recommend songs that belong to one of these genres: {genre_str}. Do not suggest songs outside these genres." if genres else ""
        pref_block = f"""
User preferences (from onboarding quiz):
- Preferred genres: {genre_str}
- Current vibe: {vibe_str}
- Era preference: {preferences.get('era', 'any')}
- Favorite artists they mentioned: {preferences.get('artists') or 'none'}
{genre_rule}
"""

    prompt = f"""You are a music recommender. Based on this listener's Spotify profile, stated preferences, and swipe history, recommend exactly ONE new song.

Profile:
- Top tracks: {profile['tracks']}
- Top artists: {profile['artists']}
- Top genres: {profile['genres']}
- Recently played: {profile['recent']}
- Followed artists: {profile['followed']}
- Saved tracks: {profile['saved']}
{pref_block}
Songs they LIKED: {liked_str}
Songs they DISLIKED: {disliked_str}
ALREADY SHOWN — DO NOT RECOMMEND ANY OF THESE UNDER ANY CIRCUMSTANCES: {seen_str}

Respond with ONLY: Song Title - Artist Name
Do not repeat any song from the already shown list above."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9
    )
    return response.choices[0].message.content.strip()

def get_track_info(song):
    if ' - ' in song:
        title, artist = song.split(' - ', 1)
    else:
        title, artist = song, ''

    art = None
    results = sp.search(q=f"track:{title} artist:{artist}", type='track', limit=1)
    items = results['tracks']['items']
    if items:
        track = items[0]
        art = track['album']['images'][0]['url'] if track['album']['images'] else None

    preview = None
    try:
        query = requests.utils.quote(f'track:"{title}" artist:"{artist}"')
        deezer = requests.get(f"https://api.deezer.com/search?q={query}&limit=1").json()
        if deezer.get('data'):
            preview = deezer['data'][0]['preview']
    except Exception:
        pass

    return {'art': art, 'preview': preview}

