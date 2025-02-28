import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

app = Flask(__name__)

# === 🔑 Load API Keys & Environment Variables ===
load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

# **Explicitly setting the Spotify user ID to "helloniam"**
SPOTIFY_USER_ID = "helloniam"

# === 🎵 Spotify Authentication (Now Using Client Credentials) ===
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))


# === 💬 Chatbot Session Data ===
session = {
    "state": "conversation",
    "preferences": {"mood": None, "genre": None}
}


def extract_songs(playlist_text):
    """Extracts song titles and artists from the LLM-generated playlist."""
    songs = []
    lines = playlist_text.split("\n")
    for line in lines:
        if line.strip() and line[0].isdigit():
            parts = line.split(" - ")
            if len(parts) == 2:
                song_title = parts[0].split(". ")[1].strip()
                artist = parts[1].strip()
                songs.append((song_title, artist))
    return songs


def search_songs(songs):
    """Searches Spotify for song URIs using Client Credentials."""
    track_uris = []
    for song, artist in songs:
        try:
            results = sp.search(q=f"track:{song} artist:{artist}", limit=1, type="track")
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                track_uris.append(tracks[0]["uri"])
        except Exception as e:
            print(f"[ERROR] Failed to search for {song} by {artist}: {e}")
    return track_uris


def create_spotify_playlist(playlist_name, track_uris):
    """Creates a Spotify playlist for 'helloniam' and adds songs."""
    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="playlist-modify-public"
        )
        sp_auth = spotipy.Spotify(auth_manager=auth_manager)
        
        playlist = sp_auth.user_playlist_create(
            user=SPOTIFY_USER_ID,  # **Explicitly using "helloniam"**
            name=playlist_name,
            public=True,
            description="A custom playlist generated by Melody 🎶"
        )

        if track_uris:
            sp_auth.playlist_add_items(playlist_id=playlist["id"], items=track_uris)

        return playlist["external_urls"]["spotify"]
    except Exception as e:
        print(f"[ERROR] Spotify playlist creation failed: {e}")
        return None


def generate_playlist(mood, genre):
    """Uses LLM to generate a playlist while avoiding content filtering issues."""
    response = generate(
        model="4o-mini",
        system="""
            You are a **music therapy assistant** named MELODY 🎶. Your job is to create **safe, fun, and engaging playlists** for users.
            - **Do NOT use words that might trigger content filtering.** Keep responses neutral and positive.
            - Generate a **10-song playlist** based on the user's mood & genre.
            - Format the response as:
              "**🎵 Playlist: [Creative Playlist Name]**\n
              1. [Song 1] - [Artist]\n
              2. [Song 2] - [Artist]\n
              ...
              10. [Song 10] - [Artist]"
        """,
        query=f"Mood: {mood}, Genre: {genre}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )

    playlist_text = response.get("response", "").strip()
    
    if not playlist_text:
        return None, "⚠️ Sorry, I couldn't generate a playlist. Try again!"
    
    return playlist_text, extract_songs(playlist_text)


def music_assistant_llm(message):
    """Handles user input while ensuring content filtering is bypassed."""
    response = generate(
        model="4o-mini",
        system="""
            You are a **music therapy assistant** named MELODY 🎶. 
            - **Ensure your response is always safe and neutral** so it doesn't trigger content filtering.
            - If the user hasn't provided both **mood** and **genre**, ask for them.
            - Once both are provided, confirm and generate a playlist.
            - **Avoid using flagged words or phrases.** Keep language clean, engaging, and positive.
            - Format the response as:  
              "Mood: [mood]\nGenre: [genre]"
        """,
        query=f"User input: '{message}'\nCurrent preferences: {session['preferences']}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )

    response_text = response.get("response", "").strip()

    if "blocked by content filtering" in response_text.lower():
        return "🎵 **Oops! Something went wrong.** Let's try again! Please share your mood and favorite genre, and I'll make a playlist for you. 😊"

    mood, genre = None, None
    if "mood:" in response_text.lower() and "genre:" in response_text.lower():
        try:
            mood = response_text.split("Mood:")[1].split("Genre:")[0].strip()
            genre = response_text.split("Genre:")[1].strip()
        except IndexError:
            return "⚠️ I couldn't determine both mood and genre. Try again!"

    if not mood or not genre:
        return response_text  

    session["preferences"]["mood"] = mood
    session["preferences"]["genre"] = genre

    playlist_text, songs = generate_playlist(mood, genre)
    if not playlist_text:
        return "⚠️ Couldn't generate a playlist. Try again!"

    track_uris = search_songs(songs)
    spotify_url = create_spotify_playlist(f"{mood} {genre} Playlist", track_uris)

    if spotify_url:
        return f"{playlist_text}\n\n🎶 **Listen on Spotify:** {spotify_url}"
    else:
        return f"{playlist_text}\n\n⚠️ Couldn't create a Spotify playlist, but here are the songs!"


@app.route('/', methods=['POST'])
def main():
    """Handles user messages and sends them to Rocket.Chat without content filtering issues."""
    data = request.get_json()
    message = data.get("text", "").strip()

    return jsonify({"text": music_assistant_llm(message)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)





















