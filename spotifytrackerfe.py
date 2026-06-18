import os
import time
import streamlit as st
from urllib.parse import urlencode
from main import (init_spotify, exchange_code, do_refresh,
                  build_profile, get_next_song, get_track_info,
                  load_history, save_history)

def _secret(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

CLIENT_ID     = _secret("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = _secret("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI  = _secret("SPOTIFY_REDIRECT_URI", "http://localhost:8501")
SCOPE = "user-top-read user-read-recently-played user-follow-read user-library-read playlist-read-private"

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap');

    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
        background-attachment: fixed;
    }
    [data-testid="stHeader"] { background: transparent; }

    .block-container {
        max-width: 480px;
        margin: 0 auto;
        padding-top: 2rem;
    }

    h1 { font-family: 'Space Grotesk', sans-serif !important; }

    h1, h2, h3, p, label, div[data-testid="stText"] {
        color: white !important;
        text-align: center;
    }
    .stCaption p { color: rgba(255,255,255,0.55) !important; text-align: center; }

    [data-testid="stForm"] {
        background: rgba(255,255,255,0.07);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 20px;
        padding: 1.5rem !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255,255,255,0.07);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 20px;
    }

    [data-testid="stPills"] button {
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        color: white !important;
        border-radius: 999px !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stPills"] button[aria-pressed="true"],
    [data-testid="stPills"] button[aria-selected="true"] {
        background: rgba(139,92,246,0.55) !important;
        border-color: rgba(167,139,250,0.7) !important;
    }

    [data-testid="stMultiSelect"] > div > div {
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 10px !important;
        color: white !important;
    }
    [data-testid="stMultiSelect"] span { color: white !important; }

    [data-testid="stTextInput"] input {
        background: rgba(255,255,255,0.9) !important;
        border: 1px solid rgba(255,255,255,0.3) !important;
        border-radius: 10px !important;
        color: black !important;
    }

    button {
        background-color: #1DB954 !important;
        color: black !important;
        border-radius: 12px !important;
        font-size: 1.4rem !important;
    }

    .stAudio { display: flex; justify-content: center; }
</style>
""", unsafe_allow_html=True)

st.title("Tinder for Spotify")

# ── OAuth callback ────────────────────────────────────────────────────────────
if "code" in st.query_params and "sp_access_token" not in st.session_state:
    code = st.query_params["code"]
    token_data = exchange_code(code, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
    if "access_token" in token_data:
        st.session_state.sp_access_token = token_data["access_token"]
        st.session_state.sp_refresh_token = token_data.get("refresh_token", "")
        st.session_state.sp_expires_at = time.time() + token_data.get("expires_in", 3600) - 60
        st.query_params.clear()
        st.rerun()
    else:
        st.error("Spotify login failed — " + token_data.get("error_description", "unknown error"))
        if st.button("Try again"):
            st.rerun()
        st.stop()

# ── Login gate ────────────────────────────────────────────────────────────────
if "sp_access_token" not in st.session_state:
    auth_url = "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "show_dialog": "true",
    })
    st.markdown("Connect your Spotify account to get personalised recommendations.")
    st.link_button("Login with Spotify", auth_url, use_container_width=True)
    st.stop()

# ── Token refresh ─────────────────────────────────────────────────────────────
if time.time() > st.session_state.get("sp_expires_at", 0):
    new_token = do_refresh(CLIENT_ID, CLIENT_SECRET, st.session_state.sp_refresh_token)
    if new_token:
        st.session_state.sp_access_token = new_token
        st.session_state.sp_expires_at = time.time() + 3600 - 60
    else:
        del st.session_state["sp_access_token"]
        st.rerun()

sp = init_spotify(st.session_state.sp_access_token)

# ── Quiz ──────────────────────────────────────────────────────────────────────
if "quiz_done" not in st.session_state:
    st.subheader("Quick taste check")
    st.caption("Help us tune your first recommendations")

    with st.form("quiz"):
        genres = st.multiselect(
            "Favorite genres",
            ["Pop", "Hip-Hop", "R&B", "Rock", "Indie", "Electronic",
             "Jazz", "Classical", "Country", "Latin", "Metal", "Folk"],
        )
        vibe = st.pills(
            "Current vibe",
            ["Energetic", "Chill", "Happy", "Melancholic", "Focused"],
            selection_mode="multi",
        )
        era = st.pills(
            "Era preference",
            ["New releases", "Mix of both", "Classics (pre-2000s)"],
            selection_mode="single",
        )
        artists = st.text_input("Any artists you're loving right now? (optional)")

        if st.form_submit_button("Let's go →", use_container_width=True):
            st.session_state.preferences = {
                "genres": genres,
                "vibe": vibe,
                "era": era,
                "artists": artists,
            }
            st.session_state.quiz_done = True
            st.rerun()

    st.stop()

# ── Profile load (once per session) ──────────────────────────────────────────
if "profile" not in st.session_state:
    with st.spinner("Loading your Spotify profile..."):
        st.session_state.profile = build_profile(sp)
    save_history([], [], [])
    st.session_state.liked = []
    st.session_state.disliked = []
    st.session_state.seen = []
    st.session_state.current_song = None

# ── Fetch next song ───────────────────────────────────────────────────────────
if st.session_state.current_song is None:
    with st.spinner("Finding your next song..."):
        st.session_state.current_song = get_next_song(
            st.session_state.profile,
            st.session_state.liked,
            st.session_state.disliked,
            st.session_state.seen,
            st.session_state.get("preferences"),
        )
        info = get_track_info(sp, st.session_state.current_song)
        st.session_state.current_art = info['art']
        st.session_state.current_preview = info['preview']

# ── Song card ─────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader(st.session_state.current_song)

    if st.session_state.current_art:
        _, img_col, _ = st.columns([1, 2, 1])
        with img_col:
            st.image(st.session_state.current_art, use_container_width=True)

    if st.session_state.current_preview:
        st.audio(st.session_state.current_preview, autoplay=True)
    else:
        st.caption("No preview available for this track.")

# ── Buttons ───────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("❌", use_container_width=True):
        st.session_state.disliked.append(st.session_state.current_song)
        st.session_state.seen.append(st.session_state.current_song)
        save_history(st.session_state.liked, st.session_state.disliked, st.session_state.seen)
        st.session_state.current_song = None
        st.rerun()
with col2:
    if st.button("⏭️", use_container_width=True):
        st.session_state.seen.append(st.session_state.current_song)
        save_history(st.session_state.liked, st.session_state.disliked, st.session_state.seen)
        st.session_state.current_song = None
        st.rerun()
with col3:
    if st.button("❤️", use_container_width=True):
        st.session_state.liked.append(st.session_state.current_song)
        st.session_state.seen.append(st.session_state.current_song)
        save_history(st.session_state.liked, st.session_state.disliked, st.session_state.seen)
        st.session_state.current_song = None
        st.rerun()

st.write(f"❤️ {len(st.session_state.liked)}  |  ✕ {len(st.session_state.disliked)}")

# ── History panel ─────────────────────────────────────────────────────────────
if st.button("View my list", use_container_width=True):
    st.session_state.show_history = not st.session_state.get("show_history", False)

if st.session_state.get("show_history"):
    with st.container(border=True):
        col_l, col_d = st.columns(2)
        with col_l:
            st.markdown("**❤️ Liked**")
            if st.session_state.liked:
                for song in st.session_state.liked:
                    st.caption(song)
            else:
                st.caption("None yet")
        with col_d:
            st.markdown("**✕ Disliked**")
            if st.session_state.disliked:
                for song in st.session_state.disliked:
                    st.caption(song)
            else:
                st.caption("None yet")
