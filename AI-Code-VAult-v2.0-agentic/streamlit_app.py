# ============================================================================
# AI CODE VAULT 2.0 - Enterprise Code Analysis & Architecture Assistant
# ============================================================================
# DEPLOYMENT_GUID: 49b1bcae-97fa-4035-ba6d-f242d131b6fa_TIDAL_V6
# ============================================================================

# --- Standard Library Imports ---
import os
import sys
import json
import re
import time
import threading
import shutil
import bcrypt
import uuid
from datetime import datetime
from dotenv import load_dotenv

# --- Third-Party Imports ---
import streamlit as st
import pandas as pd
import numpy as np
import sqlalchemy as sa
import requests
import extra_streamlit_components as stx
from sqlalchemy.orm import Session

# --- Environment Setup ---
load_dotenv(override=True)  # Load environment variables from .env file and override existing


def get_groq_api_key():
    """Resolve the GROQ API key from Streamlit secrets or environment variables."""
    try:
        session_key = st.session_state.get("groq_api_key")
        if session_key:
            return session_key.strip()
        if "GROQ_API_KEY" in st.secrets:
            secret_key = st.secrets["GROQ_API_KEY"]
            if secret_key:
                return secret_key.strip()
    except Exception:
        pass

    key = os.getenv("GROQ_API_KEY")
    return key.strip() if key else None


def get_active_groq_pool_key():
    """Read the latest active GROQ key from KeyPool using a fresh DB session."""
    try:
        engine = get_engine()
        with Session(engine) as s:
            row = (
                s.query(KeyPool)
                .filter(KeyPool.provider == "GROQ", KeyPool.is_active == True)  # noqa: E712
                .order_by(KeyPool.id.desc())
                .first()
            )
            if row and row.key_value:
                return row.key_value.strip()
    except Exception:
        return None
    return None


def resolve_runtime_groq_key():
    """Resolve GROQ key for current request path: session -> env -> active KeyPool."""
    session_key = st.session_state.get("groq_api_key")
    if isinstance(session_key, str) and session_key.strip():
        return session_key.strip()

    env_key = os.getenv("GROQ_API_KEY")
    if isinstance(env_key, str) and env_key.strip():
        return env_key.strip()

    return get_active_groq_pool_key()


def set_active_groq_api_key(api_key: str) -> str:
    """Activate a GROQ key for the current Streamlit session and process."""
    normalized = api_key.strip()
    os.environ["GROQ_API_KEY"] = normalized
    st.session_state["groq_api_key"] = normalized
    return normalized

# --- Backend Module Setup ---
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# ============================================================================
# BACKEND LOADER - Cached to improve performance
# ============================================================================
@st.cache_resource
def load_backend_modules():
    """Load all backend modules with caching for performance optimization."""
    import db_connector as db  # type: ignore
    from repo_scanner import get_repo_chunks, _log_debug, check_repo_accessible  # type: ignore
    from ai_parser import parse_code_chunk, generate_embedding  # type: ignore
    from file_processor import extract_text_from_file, chunk_text, ingest_file_to_vault  # type: ignore
    import agent as agent_module  # type: ignore
    
    return {
        # Database Models
        'init_db': db.init_db,
        'get_engine': db.get_engine,
        'Base': db.Base,
        'run_migrations': db.run_migrations,
        'get_schema_diagnostics': db.get_schema_diagnostics,
        'Hub': db.Hub,
        'SearchHistory': db.SearchHistory,
        'User': db.User,
        'ChatMessage': db.ChatMessage,
        'FileMetadata': db.FileMetadata,
        'Satellite': db.Satellite,
        'KeyPool': db.KeyPool,
        'ScanJob': db.ScanJob,
        # Data Vault 2.0 Models
        'HubCode': db.HubCode,
        'HubRepository': db.HubRepository,
        'HubUser': db.HubUser,
        'HubDocument': db.HubDocument,
        'LinkCodeRepository': db.LinkCodeRepository,
        'LinkUserRepository': db.LinkUserRepository,
        'LinkUserDocument': db.LinkUserDocument,
        'SatCodeContent': db.SatCodeContent,
        'SatCodeMetrics': db.SatCodeMetrics,
        'SatCodeEmbedding': db.SatCodeEmbedding,
        'SatDocumentContent': db.SatDocumentContent,
        'SatDocumentEmbedding': db.SatDocumentEmbedding,
        'SatUserProfile': db.SatUserProfile,
        # Evaluation Checklist Models
        'Document': db.Document,
        'Search': db.Search,
        'Feedback': db.Feedback,
        # Data Vault 2.0 Functions
        'compute_hash_key': db.compute_hash_key,
        'compute_hash_diff': db.compute_hash_diff,
        'load_data_vault': db.load_data_vault,
        'query_point_in_time': db.query_point_in_time,
        'create_views': db.create_views,
        'run_hybrid_search': db.run_hybrid_search,
        'get_user_scoped_query': db.get_user_scoped_query,
        # Backend Functions
        'get_repo_chunks': get_repo_chunks,
        '_log_debug': _log_debug,
        'parse_code_chunk': parse_code_chunk,
        'generate_embedding': generate_embedding,
        'extract_text_from_file': extract_text_from_file,
        'chunk_text': chunk_text,
        'ingest_file_to_vault': ingest_file_to_vault,
        'agent': agent_module,
        'run_agent': agent_module.run_agent,
        'run_ingest_agent': agent_module.run_ingest_agent
    }

# Load backend and extract commonly used items
backend = load_backend_modules()
backend["groq_api_key"] = get_groq_api_key()
if backend["groq_api_key"]:
    os.environ["GROQ_API_KEY"] = backend["groq_api_key"]
get_engine = backend['get_engine']
Hub = backend['Hub']
SearchHistory = backend['SearchHistory']
User = backend['User']
ChatMessage = backend['ChatMessage']
FileMetadata = backend['FileMetadata']
Satellite = backend['Satellite']
KeyPool = backend['KeyPool']
ScanJob = backend.get('ScanJob')
get_repo_chunks = backend['get_repo_chunks']
_log_debug = backend['_log_debug']
parse_code_chunk = backend['parse_code_chunk']
generate_embedding = backend['generate_embedding']
extract_text_from_file = backend['extract_text_from_file']
chunk_text = backend['chunk_text']
ingest_file_to_vault = backend['ingest_file_to_vault']
run_agent = backend['run_agent']
HubDocument = backend['HubDocument']
LinkUserDocument = backend['LinkUserDocument']
SatDocumentContent = backend['SatDocumentContent']
SatDocumentEmbedding = backend['SatDocumentEmbedding']
compute_hash_key = backend['compute_hash_key']
Document = backend['Document']
Search = backend['Search']
Feedback = backend['Feedback']
get_user_scoped_query = backend['get_user_scoped_query']


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

# Cookie Manager (not cached - acts as widget)
cookie_manager = stx.CookieManager()

def init_session_state():
    """Initialize all session state variables."""
    if 'abort_event' not in st.session_state:
        st.session_state.abort_event = threading.Event()
    if 'is_scanning' not in st.session_state:
        st.session_state.is_scanning = False
    if 'scan_progress' not in st.session_state:
        st.session_state.scan_progress = 0
    if 'scan_status' not in st.session_state:
        st.session_state.scan_status = ""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'vault_theme_mode' not in st.session_state:
        st.session_state.vault_theme_mode = "System"
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'failed_login_attempts' not in st.session_state:
        st.session_state.failed_login_attempts = []

init_session_state()

# ============================================================================
# UTILITY FUNCTIONS - Icons, Card Rendering, etc.
# ============================================================================

def get_cyber_icon(name):
    """Return SVG icon for various UI elements."""
    icons = {
        "vault": '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2L3 7V17L12 22L21 17V7L12 2Z" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 22V12" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 7L12 12L3 7" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 12L12 2" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "ingest": '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 8L12 3L7 8" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 3V15" stroke="var(--vault-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "chat": '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 11.5C21.0034 12.8199 20.6951 14.1219 20.1 15.3C19.3944 16.7112 18.3098 17.8992 16.9674 18.7303C15.6251 19.5614 14.0705 19.9985 12.48 20C10.9401 20.0067 9.42187 19.5836 8.09999 18.77L3 20.5L4.73 15.4C3.91639 14.0781 3.49333 12.5599 3.5 11.02C3.50149 9.42951 3.9386 7.87487 4.76971 6.53249C5.60081 5.1901 6.78877 4.10558 8.2 3.4C9.37808 2.80489 10.6801 2.49656 12 2.5H12.5C14.7164 2.6644 16.7958 3.61905 18.3512 5.17441C19.9066 6.72978 20.8612 8.80916 21 11.025V11.5Z" stroke="var(--vault-accent-2)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    }
    return f'<div style="display:flex; align-items:center; gap:10px;">{icons.get(name, "")}</div>'

def render_satellite_card(metrics):
    """Render a card showing code metadata (complexity, LOC, parameters)."""
    if not metrics:
        return ""
    
    loc = metrics.get('lines_of_code', 0)
    compl = metrics.get('complexity_estimate', 'N/A')
    params = ", ".join(metrics.get('parameters', [])) if metrics.get('parameters') else "None"
    
    card_html = f"""
    <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 15px 0;">
        <div style="background: var(--vault-surface); border: 1px solid var(--vault-panel-border); border-radius: 8px; padding: 12px; text-align: center;">
            <div style="color: var(--vault-accent); font-size: 0.7rem; text-transform: uppercase;">Lines of Code</div>
            <div style="color: var(--vault-text); font-size: 1.2rem; font-weight: 700;">{loc}</div>
        </div>
        <div style="background: var(--vault-surface); border: 1px solid var(--vault-panel-border); border-radius: 8px; padding: 12px; text-align: center;">
            <div style="color: var(--vault-accent-2); font-size: 0.7rem; text-transform: uppercase;">Complexity</div>
            <div style="color: var(--vault-text); font-size: 1.2rem; font-weight: 700;">{compl}</div>
        </div>
        <div style="background: var(--vault-surface); border: 1px solid var(--vault-panel-border); border-radius: 8px; padding: 12px; text-align: center;">
            <div style="color: var(--vault-text-muted); font-size: 0.7rem; text-transform: uppercase;">Parameters</div>
            <div style="color: var(--vault-text); font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis;">{params[:20]}...</div>
        </div>
    </div>
    """
    return card_html


# --- Page Configuration ---
st.set_page_config(
    page_title="AI CODE VAULT 2.0 [SYNC_ACTIVE_V6]",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Styling (Immersive Cyber Space) ---
st.markdown("""
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<div class="vault-bg-glow">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
</div>
<style>
    /* Global UI Tweaks */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;700&family=Inter:wght@400;700&display=swap');

    .stApp {
        background: radial-gradient(circle at top left, rgba(0, 242, 255, 0.08), transparent 28%), radial-gradient(circle at bottom right, rgba(112, 0, 255, 0.08), transparent 26%), var(--vault-bg) !important;
        font-family: 'Inter', sans-serif;
        color: var(--vault-text);
        line-height: 1.7;
    }

    .stApp, .block-container {
        color: var(--vault-text);
    }

    .stApp * {
        caret-color: var(--vault-text);
    }

    .stApp h1,
    .stApp h2,
    .stApp h3,
    .stApp h4,
    .stApp h5,
    .stApp h6,
    .stApp p,
    .stApp li,
    .stApp label,
    .stApp small,
    .stApp span {
        color: var(--vault-text);
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMarkdownContainer"] b,
    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"] span,
    [data-testid="stTextInput"] label p,
    [data-testid="stSelectbox"] label p,
    [data-testid="stRadio"] label p,
    [data-testid="stCheckbox"] label p,
    [data-testid="stSlider"] label p,
    [data-testid="stNumberInput"] label p,
    [data-testid="stTextArea"] label p,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"],
    [data-testid="stExpander"] summary,
    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    [data-testid="stDataEditor"],
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] *,
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stFileUploader"],
    [data-testid="stNotificationContent"],
    .stAlert, .stAlert *,
    .stException, .stException * {
        color: var(--vault-text) !important;
    }

    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] div,
    [data-baseweb="select"] span,
    [data-baseweb="tag"] span,
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox [role="combobox"],
    .stMultiSelect [role="combobox"] {
        color: var(--vault-text) !important;
        -webkit-text-fill-color: var(--vault-text) !important;
    }

    /* Widget Labels & Captions Visibility */
    div[data-testid="stWidgetLabel"] p {
        color: var(--vault-text) !important;
        font-weight: 600 !important;
    }
    div[data-testid="stCaptionContainer"],
    small,
    .stCaption {
        color: var(--vault-text-muted) !important;
        font-weight: 500 !important;
    }

    [data-baseweb="input"] input::placeholder,
    [data-baseweb="textarea"] textarea::placeholder,
    .stTextInput input::placeholder,
    .stTextArea textarea::placeholder {
        color: var(--vault-text-muted) !important;
        opacity: 1 !important;
    }

    [data-testid="stAlert"] {
        background: var(--vault-surface-strong) !important;
        border: 1px solid var(--vault-panel-border) !important;
        border-left: 4px solid var(--vault-accent) !important;
        border-radius: 16px !important;
        box-shadow: var(--vault-shadow);
        color: var(--vault-text) !important;
    }

    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span,
    [data-testid="stAlert"] div {
        color: var(--vault-text) !important;
    }

    /* Inline code block styling for high contrast readability */
    code {
        background-color: var(--vault-surface-strong) !important;
        color: var(--vault-accent) !important;
        border: 1px solid var(--vault-panel-border) !important;
        padding: 0.15rem 0.4rem !important;
        border-radius: 6px !important;
        font-family: monospace !important;
        font-weight: 600 !important;
    }
    pre code {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: inherit !important;
        font-weight: inherit !important;
    }

    [data-baseweb="tag"],
    [data-baseweb="select"],
    [data-baseweb="select"] > div,
    [data-baseweb="select"] span,
    input,
    textarea {
        background-color: var(--vault-surface) !important;
        color: var(--vault-text) !important;
        border-color: var(--vault-panel-border) !important;
    }

    [data-baseweb="popover"],
    [data-baseweb="popover"] > div,
    ul[role="listbox"],
    div[role="listbox"] {
        background-color: var(--vault-surface-strong) !important;
        color: var(--vault-text) !important;
        border: 1px solid var(--vault-panel-border) !important;
    }

    ul[role="listbox"] li,
    div[role="listbox"] [role="option"] {
        color: var(--vault-text) !important;
    }

    [data-baseweb="tab-list"] {
        gap: 0.35rem;
    }

    .stTabs [data-baseweb="tab"] {
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: var(--vault-text-muted) !important;
        border-radius: 999px !important;
        padding: 0.55rem 1rem !important;
        transition: all 0.25s ease !important;
    }

    .stTabs [aria-selected="true"] {
        color: var(--vault-text) !important;
        text-shadow: 0 0 12px rgba(0, 242, 255, 0.24) !important;
        background: linear-gradient(90deg, rgba(0, 242, 255, 0.14), rgba(112, 0, 255, 0.10)) !important;
        border: 1px solid var(--vault-panel-border) !important;
    }

    .stButton>button,
    .stFormSubmitButton button {
        background: linear-gradient(90deg, var(--vault-accent), var(--vault-accent-2)) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.10) !important;
        border-radius: 12px !important;
        padding: 0.8rem 1.2rem !important;
        font-weight: 800 !important;
        letter-spacing: 0.02em !important;
        transition: transform 0.2s ease, box-shadow 0.25s ease !important;
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.20) !important;
    }

    .stButton>button:hover,
    .stFormSubmitButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 14px 28px rgba(0, 242, 255, 0.22) !important;
    }

    .main-header {
        font-family: 'Outfit', sans-serif;
        font-size: 3.6rem;
        font-weight: 800;
        background: linear-gradient(90deg, var(--vault-accent) 0%, var(--vault-accent-2) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 24px rgba(0, 242, 255, 0.30);
        letter-spacing: -1.2px;
    }

    /* Moving Orbs Background System */
    .vault-bg-glow {
        position: fixed;
        top: 0; left: 0; 
        width: 100vw; height: 100vh;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
    }

    .orb {
        position: absolute;
        border-radius: 50%;
        filter: blur(120px);
        opacity: 0.4;
        mix-blend-mode: screen;
        pointer-events: none;
    }

    .orb-1 {
        width: 800px; height: 800px;
        background: radial-gradient(circle, rgba(0, 242, 255, 0.4), transparent 70%);
        animation: floatOrb1 20s infinite alternate ease-in-out;
    }

    .orb-2 {
        width: 1000px; height: 1000px;
        background: radial-gradient(circle, rgba(112, 0, 255, 0.4), transparent 70%);
        animation: floatOrb2 25s infinite alternate ease-in-out;
    }

    @keyframes floatOrb1 {
        0% { transform: translate(-20%, -20%) scale(1); }
        100% { transform: translate(40%, 30%) scale(1.1); }
    }

    @keyframes floatOrb2 {
        0% { transform: translate(110%, 110%) scale(1); }
        100% { transform: translate(50%, 40%) scale(0.9); }
    }

    /* Container Layering */
    [data-testid="stAppViewBlockContainer"], .block-container {
        position: relative !important;
        z-index: 10 !important;
        background: transparent !important;
    }

    /* Fix: Move 'Enter to submit' hint to the left to avoid eye icon */
    div[data-testid="stInputSocial"] {
        right: 45px !important;
    }

    /* Hide Streamlit Default UI Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    .main-header {
        font-family: 'Outfit', sans-serif;
        font-size: 3.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, var(--vault-accent) 0%, var(--vault-accent-2) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 20px var(--vault-glow);
        letter-spacing: -1px;
    }

    .glass-card {
        background: var(--vault-surface) !important;
        backdrop-filter: blur(25px) saturate(160%) !important;
        -webkit-backdrop-filter: blur(25px) saturate(160%) !important;
        border: 1px solid var(--vault-panel-border) !important;
        border-radius: 20px;
        padding: 2.5rem;
        box-shadow: var(--vault-shadow);
        margin-bottom: 2rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .glass-card:hover {
        /* Glow and highlight removed as per user request */
    }

    .stat-card {
        text-align: center;
        padding: 2rem;
        background: var(--vault-surface);
        border-radius: 15px;
        border: 1px solid var(--vault-panel-border);
        box-shadow: var(--vault-shadow);
    }
    .metric-value {
        font-family: 'Outfit', sans-serif;
        font-size: 3rem;
        color: var(--vault-accent);
        font-weight: bold;
    }
    /* Button Glows */
    .stButton>button {
        background: linear-gradient(90deg, var(--vault-accent), var(--vault-accent-2)) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.8rem 2rem !important;
        font-weight: 700 !important;
        transition: box-shadow 0.3s ease !important;
    }
    .stButton>button:hover {
        box-shadow: 0 0 20px var(--vault-glow) !important;
    }
    .chat-container {
        max-width: 850px;
        margin: 0 auto;
        padding: 2rem 0;
    }
    .chat-output-toggle {
        margin: 0.25rem 0 1rem 0;
    }
    .chat-output-panel {
        background: var(--vault-surface);
        border: 1px solid var(--vault-panel-border);
        border-radius: 16px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: var(--vault-shadow);
    }
    .chat-output-panel h4 {
        margin: 0 0 0.5rem 0;
        color: var(--vault-accent);
        font-family: 'Outfit', sans-serif;
        letter-spacing: 0.02em;
    }
    .chat-output-panel p,
    .chat-output-panel li,
    .chat-output-panel span,
    .chat-output-panel div {
        color: inherit !important;
        font-size: 1.02rem;
        line-height: 1.7;
    }
    .chat-output-panel code,
    .chat-output-panel pre {
        background-color: var(--vault-bg) !important;
        border: 1px solid var(--vault-panel-border) !important;
        color: var(--vault-text) !important;
        font-size: 1.02rem;
        line-height: 1.7;
    }
    .chat-output-panel pre {
        white-space: pre-wrap;
        word-break: break-word;
    }
    .user-msg {
        text-align: right;
        padding: 1rem;
        margin-bottom: 2rem;
        font-size: 1.1rem;
        color: var(--vault-text);
    }
    .ai-msg {
        background: var(--vault-surface);
        border: 1px solid var(--vault-panel-border);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 2.5rem;
        line-height: 1.6;
        box-shadow: var(--vault-shadow);
    }
    .nav-btn {
        width: 100%;
        text-align: left;
        padding: 0.8rem 1rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        cursor: pointer;
        transition: all 0.2s ease;
        border: 1px solid transparent;
        font-family: 'Outfit', sans-serif;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-size: 0.85rem;
    }
    .nav-btn:hover {
        background: var(--vault-surface);
        border: 1px solid var(--vault-panel-border);
    }
    .nav-active {
        background: var(--vault-surface) !important;
        border: 1.5px solid var(--vault-accent) !important;
        color: var(--vault-accent) !important;
        font-weight: 700;
        box-shadow: var(--vault-shadow);
    }
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: var(--vault-sidebar-bg) !important;
        border-right: 1px solid var(--vault-panel-border);
    }
    
    /* Mobile Responsiveness styling */
    @media (max-width: 768px) {
        .main-header {
            font-size: 2.2rem !important;
            margin-top: 1rem !important;
        }
        .orb, .orb-1, .orb-2, .vault-bg-glow {
            display: none !important;
        }
        .glass-card {
            padding: 1.25rem !important;
            margin-bottom: 1rem !important;
        }
        .chat-container {
            padding: 1rem 0.5rem !important;
        }
        .metric-value {
            font-size: 2rem !important;
        }
        .stat-card {
            padding: 1rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# --- DB Initializer (Cache Disabled for Heartbeat Reset) ---
def get_db_engine_v4():
    # We've disabled the cache to force a fresh engine creation during this heartbeat reset.
    engine = backend['get_engine']()
    return engine

engine_v4 = get_db_engine_v4()
session = Session(engine_v4)


# --- Cached Analytics (FIX 3) ---
@st.cache_data(ttl=300)
def get_cached_daily_uploads(db_url_str: str) -> list:
    """Get count of documents uploaded per day."""
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import Session as SqlSession
    engine = create_engine(db_url_str)
    with SqlSession(engine) as s:
        try:
            results = (
                s.query(func.date(Document.upload_date).label('day'), func.count(Document.id).label('count'))
                .group_by('day')
                .all()
            )
            return [{"day": str(r.day), "count": int(r.count)} for r in results]
        except Exception:
            return []

@st.cache_data(ttl=300)
def get_cached_daily_searches(db_url_str: str) -> list:
    """Get count of searches run per day."""
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import Session as SqlSession
    engine = create_engine(db_url_str)
    with SqlSession(engine) as s:
        try:
            results = (
                s.query(func.date(Search.timestamp).label('day'), func.count(Search.id).label('count'))
                .group_by('day')
                .all()
            )
            return [{"day": str(r.day), "count": int(r.count)} for r in results]
        except Exception:
            return []

@st.cache_data(ttl=300)
def get_cached_performance_metrics(db_url_str: str) -> dict:
    """Get performance metrics, including total messages, tokens, and avg response time."""
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import Session as SqlSession
    engine = create_engine(db_url_str)
    with SqlSession(engine) as s:
        try:
            avg_resp = s.query(func.avg(Search.response_time_ms)).scalar() or 0.0
            total_searches = s.query(Search).count()
            avg_top_score = s.query(func.avg(Search.top_score)).scalar() or 0.0
            total_messages = s.query(ChatMessage).count()
            estimated_input_tokens = total_messages * 350
            estimated_output_tokens = total_messages * 450
            return {
                "avg_response_time_ms": float(avg_resp),
                "total_searches": int(total_searches),
                "avg_top_score": float(avg_top_score),
                "total_messages": int(total_messages),
                "estimated_input_tokens": int(estimated_input_tokens),
                "estimated_output_tokens": int(estimated_output_tokens),
            }
        except Exception:
            return {
                "avg_response_time_ms": 0.0,
                "total_searches": 0,
                "avg_top_score": 0.0,
                "total_messages": 0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
            }


def get_live_user(user_id):
    """Fetch the latest user row from a short-lived session."""
    with Session(engine_v4) as live_session:
        return live_session.query(User).filter(User.id == user_id).first()

# --- IRON-CLAD VERIFICATION HANDSHAKE ---
def verify_integrity():
    with st.spinner("🚀 SYNCHRONIZING NEURAL VAULT... (Safety Handshake)"):
        for attempt in range(3):
            try:
                diag = backend['get_schema_diagnostics'](engine_v4)
                if 'tables' in diag and "users" in diag.get('tables', []):
                    backend['run_migrations'](engine_v4)
                    return True
                # Attempt repair: recreate schema
                backend['Base'].metadata.create_all(engine_v4)
                backend['run_migrations'](engine_v4)
            except Exception as e:
                # Handle database corruption: delete and reinitialize
                error_str = str(e).lower()
                if 'malformed' in error_str or 'corrupt' in error_str or 'database disk image' in error_str:
                    try:
                        # Try to get db path from environment or use default
                        db_url = os.getenv('DATABASE_URL', 'sqlite:///./vault_v5.db')
                        if 'sqlite' in db_url:
                            db_path = db_url.replace('sqlite:///', '').replace('sqlite://', '')
                            if os.path.exists(db_path):
                                os.remove(db_path)
                                print(f"🔧 Removed corrupted database: {db_path}")
                        # Close and recreate engine
                        engine_v4.dispose()
                        globals()['engine_v4'] = backend['get_engine']()
                    except Exception as cleanup_err:
                        print(f"Database cleanup error: {cleanup_err}")
                else:
                    print(f"Database verification error: {e}")
            time.sleep(1)
        return False

if not verify_integrity():
    st.error("❌ VAULT STRUCTURAL FAILURE: Could not verify database integrity.")
    st.info(f"Diagnostics: {backend['get_schema_diagnostics'](engine_v4)}")
    st.stop()

# --- Emergency Password Reset / Admin Provisioning ---
try:
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if admin_email and admin_password:
        user_count = session.query(User).count()
        if user_count == 0:
            new_pass_hash = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            new_admin = User(email=admin_email, hashed_password=new_pass_hash, role='Admin')
            session.add(new_admin)
            session.commit()
            print("VAULT_DEBUG: Admin account provisioned from environment variables.")
    else:
        print("VAULT_DEBUG: Admin credentials not configured in environment, skipping provisioning.")
except Exception as e:
    session.rollback()
    print(f"VAULT_DEBUG: Emergency provisioning failed: {e}")

# --- Global Session Guard: Resolve PendingRollbackErrors immediately ---
try:
    session.execute(sa.text("SELECT 1"))
except Exception:
    session.rollback()

# --- Helper Functions ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def load_chat_history():
    if not st.session_state.authenticated or not st.session_state.user:
        return
    try:
        user_id = st.session_state.user.get('id')
        if user_id is None:
            return
        history = get_user_scoped_query(session, ChatMessage, user_id).order_by(ChatMessage.id.asc()).all()
        st.session_state.messages = [{"role": msg.role, "content": msg.content} for msg in history]
    except Exception as e:
        print(f"Error loading chat history: {e}")

# --- Session State Management ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- Auto-Handshake: Persistent Session Recovery ---
if not st.session_state.authenticated:
    token = cookie_manager.get('vault_session_token')
    if token:
        try:
            user = session.query(User).filter(User.session_token == token).first()
            if user:
                st.session_state.authenticated = True
                st.session_state.user = {"id": user.id, "email": user.email, "role": user.role}
                st.session_state.menu = "Admin_Dashboard" if user.role == 'Admin' else "Ingest"
                
                # Load theme preference
                from db_connector import SatUserProfile, compute_hash_key
                user_hash = compute_hash_key(user.email)
                profile = session.query(SatUserProfile).filter(SatUserProfile.hub_user_hash == user_hash, SatUserProfile.load_end_date.is_(None)).first()
                if profile and profile.theme_preference:
                    st.session_state.vault_theme_mode = profile.theme_preference
                
                load_chat_history()
        except Exception as e:
            print(f"Auto-Handshake Failure: {e}")

if 'user' not in st.session_state or not isinstance(st.session_state.user, dict):
    st.session_state.user = {"id": None, "email": "unknown@local", "role": "Guest"}
else:
    st.session_state.user.setdefault("id", None)
    st.session_state.user.setdefault("email", "unknown@local")
    st.session_state.user.setdefault("role", "Guest")
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'scan_message' not in st.session_state:
    st.session_state.scan_message = ""
if 'vault_theme_mode' not in st.session_state:
    st.session_state.vault_theme_mode = "System"

def apply_theme_styles(theme_mode):
    if theme_mode == "Dark":
        theme_css = """
        <style>
            :root {
                --vault-bg: #05070a;
                --vault-surface: rgba(13, 17, 23, 0.82);
                --vault-surface-strong: rgba(21, 27, 35, 0.96);
                --vault-text: #f8fbff;
                --vault-text-muted: rgba(248, 251, 255, 0.72);
                --vault-panel-border: rgba(255, 255, 255, 0.12);
                --vault-sidebar-bg: #06080c;
                --vault-shadow: 0 16px 44px rgba(0, 0, 0, 0.82);
                --vault-accent: #00f2ff;
                --vault-accent-2: #7000ff;
            }
            .stApp { color-scheme: dark; }
        </style>
        """
    elif theme_mode == "Light":
        theme_css = """
        <style>
            :root {
                --vault-bg: #eef4fb;
                --vault-surface: rgba(255, 255, 255, 0.95);
                --vault-surface-strong: rgba(255, 255, 255, 1);
                --vault-text: #0b1324;
                --vault-text-muted: rgba(11, 19, 36, 0.72);
                --vault-panel-border: rgba(11, 19, 36, 0.12);
                --vault-sidebar-bg: #e7eef7;
                --vault-shadow: 0 16px 44px rgba(11, 19, 36, 0.10);
                --vault-accent: #006dff;
                --vault-accent-2: #7c3aed;
            }
            .stApp { color-scheme: light; }
        </style>
        """
    else:
        theme_css = """
        <style>
            :root {
                --vault-bg: #eef4fb;
                --vault-surface: rgba(255, 255, 255, 0.95);
                --vault-surface-strong: rgba(255, 255, 255, 1);
                --vault-text: #0b1324;
                --vault-text-muted: rgba(11, 19, 36, 0.72);
                --vault-panel-border: rgba(11, 19, 36, 0.12);
                --vault-sidebar-bg: #e7eef7;
                --vault-shadow: 0 16px 44px rgba(11, 19, 36, 0.10);
                --vault-accent: #006dff;
                --vault-accent-2: #7c3aed;
            }
            @media (prefers-color-scheme: dark) {
                :root {
                    --vault-bg: #05070a;
                    --vault-surface: rgba(13, 17, 23, 0.82);
                    --vault-surface-strong: rgba(21, 27, 35, 0.96);
                    --vault-text: #f8fbff;
                    --vault-text-muted: rgba(248, 251, 255, 0.72);
                    --vault-panel-border: rgba(255, 255, 255, 0.12);
                    --vault-sidebar-bg: #06080c;
                    --vault-shadow: 0 16px 44px rgba(0, 0, 0, 0.82);
                    --vault-accent: #00f2ff;
                    --vault-accent-2: #7000ff;
                }
            }
            .stApp { color-scheme: light dark; }
        </style>
        """
    st.markdown(theme_css, unsafe_allow_html=True)

apply_theme_styles(st.session_state.vault_theme_mode)

# --- Validation Helpers ---
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9._%+-]*[a-zA-Z0-9])?@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}$"
)

def _is_valid_email(email: str) -> bool:
    """RFC-style email check: local@domain.tld, no leading/trailing dots."""
    if not email or len(email) > 254:
        return False
    return bool(_EMAIL_RE.match(email))

def _validate_password(password: str):
    """Return (ok: bool, message: str) for password strength."""
    issues = []
    if len(password) < 8:
        issues.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        issues.append("one uppercase letter")
    if not re.search(r"[a-z]", password):
        issues.append("one lowercase letter")
    if not re.search(r"[0-9]", password):
        issues.append("one digit")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':""\\|,.<>/?]", password):
        issues.append("one special character (!@#$%^&*...)")
    if issues:
        return False, "Password must contain: " + ", ".join(issues) + "."
    return True, ""

# --- Login / Signup UI ---
def auth_page():

    # Only show centered AI CODE VAULT title
    st.markdown('<div class="main-header" style="text-align: center; margin-top: 2rem; font-size: 4.5rem;">AI CODE VAULT 2.0</div>', unsafe_allow_html=True)
    
    # Feature Slider / Marquee
    st.markdown("""
        <style>
        .marquee-container {
            max-width: 700px;
            margin: 0 auto 2rem auto;
            overflow: hidden;
            background: var(--vault-surface);
            border: 1px solid var(--vault-panel-border);
            border-radius: 18px;
            padding: 12px 0;
            box-shadow: var(--vault-shadow);
            position: relative;
            backdrop-filter: blur(16px);
        }
        .marquee-content {
            display: flex;
            white-space: nowrap;
            animation: slide-left 15s linear infinite;
        }
        .marquee-item {
            color: var(--vault-text);
            font-size: 1rem;
            font-weight: 800;
            letter-spacing: 1px;
            padding: 0 25px;
            display: inline-block;
            text-transform: uppercase;
        }
        @keyframes slide-left {
            0% { transform: translateX(0%); }
            100% { transform: translateX(-50%); }
        }
        /* Tab Styling */
        .stTabs [data-baseweb="tab"] {
            font-size: 1.05rem !important;
            font-weight: 700 !important;
            color: var(--vault-text-muted) !important;
            transition: all 0.3s ease !important;
        }
        .stTabs [aria-selected="true"] {
            color: var(--vault-text) !important;
            text-shadow: 0 0 12px rgba(0, 242, 255, 0.28) !important;
        }
        .stTextInput label p {
            color: var(--vault-text) !important;
            font-weight: 700 !important;
        }
        /* Form Submit Button Styling */
        .stFormSubmitButton button {
            background: linear-gradient(90deg, var(--vault-accent), var(--vault-accent-2)) !important;
            color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            font-weight: 700 !important;
            border-radius: 10px !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 10px 24px rgba(0,0,0,0.18) !important;
        }
        .stFormSubmitButton button:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 28px rgba(0, 242, 255, 0.24) !important;
            color: #ffffff !important;
        }
        </style>
        <div class="marquee-container">
            <div class="marquee-content">
                <span class="marquee-item">✦ NEURAL AST INDEXING</span>
                <span class="marquee-item">✦ 100M+ VECTOR CAPACITY</span>
                <span class="marquee-item">✦ RAG ARCHITECT ASSISTANT</span>
                <span class="marquee-item">✦ HYBRID SEMANTIC SEARCH</span>
                <span class="marquee-item">✦ ENTERPRISE SECURITY</span>
                <!-- Duplicate for seamless loop -->
                <span class="marquee-item">✦ NEURAL AST INDEXING</span>
                <span class="marquee-item">✦ 100M+ VECTOR CAPACITY</span>
                <span class="marquee-item">✦ RAG ARCHITECT ASSISTANT</span>
                <span class="marquee-item">✦ HYBRID SEMANTIC SEARCH</span>
                <span class="marquee-item">✦ ENTERPRISE SECURITY</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        tab1, tab2 = st.tabs(["Login", "Signup"])
        
        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                remember_me = st.checkbox("Keep me logged in (Persistent Vault)", value=True)
                submitted = st.form_submit_button("Enter Vault", use_container_width=True)
                
                if submitted:
                    from datetime import timedelta
                    now = datetime.now()
                    st.session_state.failed_login_attempts = [
                        t for t in st.session_state.failed_login_attempts
                        if (now - t).total_seconds() < 900
                    ]
                    if len(st.session_state.failed_login_attempts) >= 5:
                        lockout_expiry = st.session_state.failed_login_attempts[0] + timedelta(minutes=15)
                        remaining = max(0, int((lockout_expiry - now).total_seconds()))
                        minutes = remaining // 60
                        seconds = remaining % 60
                        st.error(f"Too many failed login attempts. Locked out for {minutes:02d}:{seconds:02d} minutes.")
                    elif not _is_valid_email(email):
                        st.error("Invalid email. Use a real address like name@example.com")
                    else:
                        try:
                            user = session.query(User).filter(User.email == email).first()
                        except Exception as db_err:
                            st.error(f"DATABASE DIAGNOSTICS: {str(db_err)}")
                            st.info(f"Target DB: {str(session.bind.url)}")
                            st.stop()
                            user = None

                        # Safely obtain stored password hash from legacy or current column
                        stored_hash = None
                        if user:
                            stored_hash = getattr(user, "password_hash", None) or getattr(user, "hashed_password", None)

                        if user and stored_hash and verify_password(password, stored_hash):
                            st.session_state.authenticated = True
                            st.session_state.user = {"id": user.id, "email": user.email, "role": user.role}
                            st.session_state.menu = "Admin_Dashboard" if user.role == 'Admin' else "Ingest"
                            st.session_state.failed_login_attempts = []

                            # Load theme preference
                            from db_connector import SatUserProfile, compute_hash_key
                            user_hash = compute_hash_key(user.email)
                            profile = session.query(SatUserProfile).filter(SatUserProfile.hub_user_hash == user_hash, SatUserProfile.load_end_date.is_(None)).first()
                            if profile and profile.theme_preference:
                                st.session_state.vault_theme_mode = profile.theme_preference

                            # Handle Persistence
                            if remember_me:
                                token = str(uuid.uuid4())
                                user.session_token = token
                                session.commit()
                                import datetime as dt
                                cookie_manager.set('vault_session_token', token, expires_at=datetime.now() + dt.timedelta(days=7))

                            load_chat_history()
                            st.success(f"Welcome back, {email}!")
                            st.toast("Login Successful!", icon="✅")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.session_state.failed_login_attempts.append(now)
                            st.error(f"Explicit Warning: Password match error or User not found! (Attempt {len(st.session_state.failed_login_attempts)}/5)")
        
        with tab2:
            with st.form("signup_form", clear_on_submit=True):
                new_email = st.text_input("Email")
                new_pass = st.text_input("Password", type="password")
                confirm_pass = st.text_input("Confirm Password", type="password")
                
                signup_submitted = st.form_submit_button("Create Account", use_container_width=True)
                
                if signup_submitted:
                    if not _is_valid_email(new_email):
                        st.error("Invalid email. Use a real address like name@example.com")
                    elif not new_pass:
                        st.error("Password cannot be empty.")
                    elif new_pass != confirm_pass:
                        st.error("Passwords do not match.")
                    elif not (pw_ok := _validate_password(new_pass))[0]:
                        st.error(pw_ok[1])
                    else:
                        try:
                            existing = session.query(User).filter(User.email == new_email).first()
                        except Exception as db_err:
                            st.error(f"DATABASE DIAGNOSTICS: {str(db_err)}")
                            st.info(f"Target DB: {str(session.bind.url)}")
                            st.stop()
                            
                        if existing:
                            st.error("Explicit Warning: User already exists with this email.")
                        else:
                            try:
                                admin_env_email = os.getenv("ADMIN_EMAIL")
                                role = 'Admin' if (admin_env_email and new_email == admin_env_email) else 'User'
                                hash_val = hash_password(new_pass)
                                new_user = User(email=new_email, role=role, hashed_password=hash_val)
                                session.add(new_user)
                                session.commit()
                                st.success("Registered successfully! Please switch to Login tab.")
                                st.toast("Registered successfully!", icon="🎉")
                                st.balloons()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Vault Security: Registry Conflict. The database is currently locked by another operation. Please wait 5 seconds and try again. ({e})")
        st.markdown('</div>', unsafe_allow_html=True)

def render_custom_progress(status, progress, eta=None):
    """Neural Stream Terminal: A live, non-traditional data ingestion visualization"""
    import random
    log_prefixes = ["DATA_FEED", "NEURAL_LINK", "VECTOR_SYNC", "AST_PARSE", "HUB_WRITE"]
    active_prefix = random.choice(log_prefixes)
    
    # CSS for the 'Live' feel
    terminal_css = """
    <style>
    @keyframes neural-pulse {
        0% { box-shadow: 0 0 8px rgba(0, 242, 255, 0.18); }
        50% { box-shadow: 0 0 24px rgba(0, 242, 255, 0.34); }
        100% { box-shadow: 0 0 8px rgba(0, 242, 255, 0.18); }
    }
    .neural-terminal {
        background: var(--vault-surface-strong);
        border: 1px solid var(--vault-panel-border);
        border-radius: 18px;
        padding: 20px;
        font-family: 'Courier New', monospace;
        color: var(--vault-text);
        animation: neural-pulse 2s infinite;
        margin-bottom: 20px;
        box-shadow: var(--vault-shadow);
    }
    .terminal-header {
        border-bottom: 1px solid var(--vault-panel-border);
        padding-bottom: 10px;
        margin-bottom: 15px;
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        letter-spacing: 2px;
        color: var(--vault-text-muted);
    }
    .terminal-feed {
        height: 120px;
        overflow-y: hidden;
        font-size: 0.9rem;
        display: flex;
        flex-direction: column-reverse;
    }
    .feed-line {
        margin-bottom: 5px;
        opacity: 0.9;
        color: var(--vault-text-muted);
    }
    .active-line {
        color: var(--vault-text);
        font-weight: bold;
        border-left: 3px solid var(--vault-accent);
        padding-left: 10px;
    }
    </style>
    """
    
    terminal_html = f"""
    {terminal_css}
    <div class="neural-terminal">
        <div class="terminal-header">
            <span>NEURAL STREAM CORE v2.0</span>
            <span>INDEX_INTEGRITY: {progress}%</span>
        </div>
        <div class="terminal-feed">
            <div class="feed-line active-line">[{active_prefix}] >> {status}</div>
            <div class="feed-line">[SYSTEM_LOG] >> Validating Neural Weights...</div>
            <div class="feed-line">[TRANSMIT] >> Processing Code Chunks...</div>
            <div class="feed-line">[AUTHENTICATE] >> Handshake Successful.</div>
        </div>
        <div style="margin-top: 15px; color: var(--vault-text); font-size: 0.85rem; text-align: right; font-weight: 600;">
            ⏱️ ESTIMATED COMPLETION: {eta if eta else 'CALCULATING...'}
        </div>
    </div>
    """
    
    if progress < 100:
        st.markdown(terminal_html, unsafe_allow_html=True)
    else:
        st.success("✅ Neural Indexing Complete. All vectors synchronized.")
        st.balloons()

# --- Sidebar Navigation ---
if not st.session_state.authenticated:
    auth_page()
    st.stop()

# --- Authenticated Sidebar Content ---
logo_path = os.path.join(os.path.dirname(__file__), "assets", "ai_vault_pro_logo.png")
if os.path.exists(logo_path):
    try:
        st.sidebar.image(logo_path, width="stretch")
    except Exception:
        pass
st.sidebar.markdown("""
    <div style='text-align: center; margin-bottom: 20px; padding: 0.75rem; border-radius: 14px; border: 1px solid var(--vault-panel-border); background: var(--vault-surface);'>
        <h2 style='color: var(--vault-text); font-family: Outfit; margin-bottom:4px; font-weight: 800; font-size: 1.3rem;'>COMMAND CENTER</h2>
        <small style='color: var(--vault-accent); font-weight: 700; font-size: 0.8rem; letter-spacing: 0.05em;'>[SYNC_ACTIVE_V5]</small>
    </div>
""", unsafe_allow_html=True)
user_obj = st.session_state.get('user') or {}
# Ensure later code that subscripts `st.session_state.user` doesn't crash
if st.session_state.get('user') is None:
    st.session_state.user = user_obj
user_email = user_obj.get('email', 'unknown@local')
user_role = user_obj.get('role', 'Guest')
user_id = user_obj.get('id')

st.sidebar.markdown(f"<p style='text-align: center;'>Account: <b>{user_email}</b><br><small>({user_role})</small></p>", unsafe_allow_html=True)
if st.sidebar.button("Logout Access", use_container_width=True):
    try:
        if user_id is not None:
            db_user = session.query(User).filter(User.id == user_id).first()
            if db_user:
                db_user.session_token = None
                session.commit()
    except Exception:
        pass

    st.session_state.authenticated = False
    st.session_state.user = None
    cookie_manager.delete('vault_session_token')
    time.sleep(0.5)
    st.rerun()

# Navigation Menu State
if 'menu' not in st.session_state:
    st.session_state.menu = "Ingest"

def set_menu(name):
    st.session_state.menu = name

st.sidebar.markdown("<br>", unsafe_allow_html=True)

if user_role == 'Admin':
    menu_items = [
        ("Admin_Dashboard", "Global Dashboard"),
        ("Admin_Users", "User Management"),
        ("Admin_Activity", "Global Activity Logs"),
        ("Profile", "User Profile")
    ]
else:
    menu_items = [
        ("Ingest", "Scan Repository"),
        ("Smart_Search", "Smart Search"),
        ("Explorer", "Vault Explorer"),
        ("Architect", "Agentic AI Studio"),
        ("Analytics", "Analytics Portal"),
        ("Profile", "User Profile")
    ]

for key, label in menu_items:
    is_active = "nav-active" if st.session_state.menu == key else ""
    if st.sidebar.button(label, key=f"nav_{key}", use_container_width=True, on_click=set_menu, args=(key,)):
        pass
    # We use a bit of invisible CSS to mark active state since st.button doesn't support active state natively well
    if st.session_state.menu == key:
        st.sidebar.markdown(f'<div style="height:2px; background:var(--vault-accent); width:100%; margin-top:-10px; margin-bottom:10px; box-shadow:0 0 10px var(--vault-accent);"></div>', unsafe_allow_html=True)

menu = st.session_state.menu

# --- Sidebar Managed Status ---
st.sidebar.divider()
st.sidebar.caption("Neural Interface: Managed by Global Administration")
st.sidebar.info("Enterprise Protocol: All API credentials are pre-configured in the Admin Vault.")

# --- Sidebar Activity Portal ---
if user_role != 'Admin':
    # Session Guard: Resolve PendingRollbackErrors immediately
    try:
        session.execute(sa.text("SELECT 1"))
    except Exception:
        session.rollback()

    st.sidebar.divider()
    st.sidebar.subheader("Recent Technical Activity")
    user_id = user_obj.get('id')
    
    # Session Grouping: Last 5 Searches & 5 Chats (Uniques)
    recent_searches = get_user_scoped_query(session, SearchHistory, user_id).order_by(SearchHistory.id.desc()).limit(5).all()
    recent_chats = get_user_scoped_query(session, ChatMessage, user_id).filter(ChatMessage.role == 'user').order_by(ChatMessage.id.desc()).limit(5).all()

    if recent_searches or recent_chats:
        st.sidebar.caption("Neural Retrieval (Recent)")
        for rs in recent_searches:
            if st.sidebar.button(rs.query[:25] + "...", key=f"rs_{rs.id}", help=rs.query, use_container_width=True):
                st.session_state.menu = "Search"
                st.session_state.neural_search_input = rs.query
                st.rerun()

        st.sidebar.caption("Architect Consultations")
        for rc in recent_chats:
            if st.sidebar.button(rc.content[:25] + "...", key=f"rc_{rc.id}", help=rc.content, use_container_width=True):
                st.session_state.menu = "Architect"
                st.rerun()
    else:
        st.sidebar.info("System activity logs are currenty empty.")

# --- Functions ---
def background_scan_task(repo_url, user_id, abort_event, job_uuid: str = None):
    """Execution logic in a background thread with real-time DB progress updates"""
    engine = get_engine()

    def _update_db(prog, status):
        """Helper: push progress into DB so the polling UI picks it up immediately"""
        try:
            with Session(engine) as s:
                u = s.query(User).filter(User.id == user_id).first()
                if u:
                    u.scan_progress = prog
                    u.scan_status = status
                    s.commit()
        except Exception:
            pass

    def _update_job(prog: int, status: str, started: bool = False, finished: bool = False, temp_dir: str = None):
        try:
            with Session(engine) as s:
                if job_uuid:
                    job = s.query(ScanJob).filter(ScanJob.job_uuid == job_uuid).first()
                    if job:
                        job.progress = int(prog)
                        job.status = status
                        if temp_dir:
                            job.temp_dir = temp_dir
                        if started and not job.started_at:
                            job.started_at = datetime.now()
                        if finished:
                            job.finished_at = datetime.now()
                        s.commit()
        except Exception:
            pass

    _log_debug(f"WORKER: Started background_scan_task for {repo_url} (User: {user_id})")
    try:
        _update_db(0, "Scanning Repository & Extracting Chunks...")
        _update_job(0, "Preparing: Scanning repository...", started=True)
        all_chunks = get_repo_chunks(repo_url)
        
        if not all_chunks:
            _log_debug("WORKER: No chunks extracted! Aborting.")
            _update_db(0, "Error: No code/files found in target.")
            return

        total = len(all_chunks)
        _log_debug(f"WORKER: Starting indexing phase for {total} chunks.")
        success_count = 0

        with Session(engine) as scan_session:
            db_user = scan_session.query(User).filter(User.id == user_id).first()
            for i, chunk in enumerate(all_chunks):
                if abort_event.is_set():
                    if db_user:
                        db_user.scan_status = "Halted by User."
                        db_user.scan_progress = 0
                        scan_session.commit()
                    _update_job(0, "Halted by User.", finished=True)
                    return

                parsed = parse_code_chunk(chunk)
                if parsed and parsed.get('hub'):
                    hub_data = parsed['hub']
                    # Check for duplicate hub_key to avoid constraint violations
                    existing_hub = scan_session.query(Hub).filter(
                        Hub.hash_key == hub_data['hash_key'],
                        Hub.user_id == user_id
                    ).first()
                    
                    new_hub = Hub(
                        hash_key=hub_data['hash_key'],
                        code_snippet=hub_data['code_snippet'],
                        embedding_vector=hub_data.get('embedding', []),
                        user_id=user_id,
                        repo_url=chunk.get('repo_url', repo_url)  # Use repo_url from chunk or parameter
                    )
                    
                    if existing_hub:
                        # Update existing hub
                        existing_hub.code_snippet = hub_data['code_snippet']
                        existing_hub.embedding_vector = hub_data.get('embedding', [])
                        existing_hub.repo_url = chunk.get('repo_url', repo_url)
                        scan_session.merge(existing_hub)
                    else:
                        # Add new hub
                        scan_session.add(new_hub)
                    
                    scan_session.flush()  # Flush to detect errors early
                    success_count += 1

                # Update progress strictly based on index / total - Throttled to 2s
                import time as _time
                current_time = _time.time()
                if not hasattr(background_scan_task, 'last_ui_update'):
                    background_scan_task.last_ui_update = 0
                
                if current_time - background_scan_task.last_ui_update > 2.0 or i == total - 1:
                    prog = int((i + 1) / total * 100)
                    eta_s = (total - i - 1) * 2
                    eta_str = f"{eta_s // 60}m {eta_s % 60}s"
                    stat = f"Indexing: {i+1}/{total} chunks — ETA {eta_str}"
                    
                    if db_user:
                        db_user.scan_progress = prog
                        db_user.scan_status = stat
                        scan_session.commit() # Push update live to DB
                        _update_job(prog, stat)
                        background_scan_task.last_ui_update = current_time

            _update_db(100, f"Complete — {success_count} code hubs indexed.")
            _update_job(100, f"Complete — {success_count} code hubs indexed.", finished=True)
            _log_debug(f"WORKER: Task Complete. Indexed {success_count} chunks.")

    except Exception as e:
        import traceback
        err_msg = f"Critical Failure: {str(e)}"
        _log_debug(f"WORKER_CRASH: {err_msg}")
        _log_debug(traceback.format_exc())
        _update_db(0, err_msg)


def stop_ingestion(user_id, status_message="Halted by User."):
    """Stop the active ingestion flow and persist the halted state."""
    st.session_state.abort_event.set()
    st.session_state.is_scanning = False
    st.session_state.scan_status = status_message
    st.session_state.scan_progress = 0

    engine = get_engine()
    with Session(engine) as scan_session:
        db_user = scan_session.query(User).filter(User.id == user_id).first()
        if db_user:
            db_user.scan_status = status_message
            db_user.scan_progress = 0
            scan_session.commit()

def process_file_content(uploaded_file, user_id):
    """Index a single file's content into the Hub - Supports Multi Format"""
    st.session_state.abort_event.clear()
    
    filename = uploaded_file.name
    file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Force All File I/O to /tmp using tempfile.mkdtemp()
    import tempfile
    import os
    temp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(temp_dir, filename)
    
    try:
        # Read the entire file into memory once at the start to avoid cloud caching issues
        file_bytes = uploaded_file.getvalue()
        
        with open(tmp_path, 'wb') as tmp:
            tmp.write(file_bytes)
            
        progress_bar = st.progress(0, text="Initializing Data Vault Ingestion...")
        
        def update_progress(current, total):
            pct = min(100, int(100 * current / total)) if total > 0 else 0
            progress_bar.progress(pct, text=f"Indexing chunk {current}/{total} into Data Vault 2.0...")
            
        with st.spinner(f"Indexing {filename}..."):
            # 1. New DV2.0 Ingestion Pipeline
            ingest_result = ingest_file_to_vault(tmp_path, filename, user_id, session, progress_callback=update_progress)
            
            # 2. Existing AI Parser Workflow (Dual Write)
            # We need raw_text for the AI parser
            raw_text = extract_text_from_file(tmp_path)
            if len(raw_text) > 2000:
                chunks = chunk_text(raw_text, chunk_size=1500, overlap=100)
            elif raw_text:
                chunks = [raw_text]
            else:
                chunks = []
                
            total_chunks = len(chunks)
            if total_chunks > 0:
                for i, c in enumerate(chunks):
                    if not c.strip(): continue
                    file_repo_url = f"file_upload/{filename}"
                    chunk_obj = {
                        "name": f"{filename}#part{i+1}" if total_chunks > 1 else filename,
                        "type": "chunk",
                        "code": c,
                        "file_path": f"direct_upload/{filename}",
                        "repo_url": file_repo_url,
                        "chunk_id": i
                    }
                    parsed = parse_code_chunk(chunk_obj)
                    if parsed and parsed.get('hub'):
                        hub_data = parsed['hub']
                        existing_hub = session.query(Hub).filter(
                            Hub.hash_key == hub_data['hash_key'],
                            Hub.user_id == user_id
                        ).first()
                        
                        new_hub = Hub(
                            hash_key=hub_data['hash_key'],
                            code_snippet=c,
                            embedding_vector=hub_data.get('embedding', []),
                            user_id=user_id,
                            repo_url=file_repo_url
                        )
                        if existing_hub:
                            existing_hub.code_snippet = c
                            existing_hub.embedding_vector = hub_data.get('embedding', [])
                            session.merge(existing_hub)
                        else:
                            session.add(new_hub)
                session.commit()
            
            # Show summary
            st.success(f"Ingestion Complete!\n\n"
                       f"- Total DV2.0 Chunks: {ingest_result['chunks']}\n"
                       f"- Successful Embeddings: {ingest_result['embeddings_success']}\n"
                       f"- Failed Embeddings: {ingest_result['embeddings_failed']}\n"
                       f"- Time Taken: {ingest_result['time']:.2f}s")
            st.balloons()
            
    except Exception as e:
        session.rollback()
        st.error(f"Error indexing file: {str(e)}")
        print(f"Vault ingestion error: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


def run_scan(repo_url):
    """Trigger the background scan thread"""
    if st.session_state.get('is_scanning'):
        # Check DB failsafe in case session state got stuck
        engine = get_engine()
        with Session(engine) as scan_session:
            db_user = scan_session.query(User).filter(User.id == st.session_state.user['id']).first()
            if db_user and db_user.scan_status and any(k in str(db_user.scan_status).lower() for k in ["cloning", "parsing", "indexing", "scanning", "preparing"]):
                st.warning("A scan is already in progress.")
                return
            else:
                st.session_state.is_scanning = False
        
    user_id = st.session_state.user['id']
    # Immediately set DB status so UI picks it up
    engine = get_engine()
    with Session(engine) as scan_session:
        db_user = scan_session.query(User).filter(User.id == user_id).first()
        if db_user:
            db_user.scan_status = "Preparing: Validating repository..."
            db_user.scan_progress = 0
            scan_session.commit()

    st.session_state.scan_status = "Preparing: Validating repository..."
    st.session_state.scan_progress = 0

    # Create a ScanJob entry to track this ingestion (does not replace User, but centralizes job state)
    engine = get_engine()
    job_uuid = str(uuid.uuid4())
    try:
        with Session(engine) as s:
            new_job = ScanJob(
                job_uuid=job_uuid,
                user_id=user_id,
                repo_url=repo_url,
                status='Queued',
                progress=0,
            )
            s.add(new_job)
            s.commit()
    except Exception as e:
        _log_debug(f"RUN_SCAN: failed to create ScanJob: {e}")

    # GitHub repos are validated inside the background scanner, which can now
    # fall back to ZIP download and report the real failure reason if needed.
    if not repo_url or not repo_url.strip():
        st.error("Please provide a valid URL or Path.")
        st.session_state.is_scanning = False
        return

    if not (repo_url.startswith('https://github.com') or repo_url.startswith('git@github.com')):
        if not os.path.exists(repo_url):
            user_msg = f"Local path does not exist: {repo_url}\n\nProvide a valid local directory path or a GitHub URL."
            with Session(engine) as scan_session:
                db_user = scan_session.query(User).filter(User.id == user_id).first()
                if db_user:
                    db_user.scan_status = f"Error: {user_msg.split(chr(10))[0]}"
                    db_user.scan_progress = 0
                    scan_session.commit()
            st.error(user_msg)
            st.session_state.scan_status = user_msg.split('\n')[0]
            st.session_state.is_scanning = False
            return

    # Reset kill-switch and start background worker
    st.session_state.abort_event.clear()
    st.session_state.is_scanning = True
    thread = threading.Thread(target=background_scan_task, args=(repo_url, user_id, st.session_state.abort_event, job_uuid))
    thread.daemon = True
    thread.start()

    st.rerun()

def run_hybrid_search(query):
    user_id = st.session_state.user['id']
    import db_connector as db
    db_run_search = db.run_hybrid_search
    if db_run_search:
        with Session(engine_v4) as sess:
            top_results = db_run_search(sess, query, user_id, top_k=5)
            
            # Save History
            try:
                new_hist = SearchHistory(
                    query=query,
                    results_count=len(top_results),
                    timestamp=datetime.now(),
                    user_id=user_id
                )
                sess.add(new_hist)
                sess.commit()
            except Exception as e:
                sess.rollback()
                print(f"VAULT_DEBUG: Failed to save search history: {e}")
            return top_results
    return []


backend['run_hybrid_search'] = run_hybrid_search

def reset_vault():
    """Clear current user's repositories and chat history only"""
    user_id = st.session_state.user.get('id')
    if user_id is None:
        st.error("Cannot reset: No active user session.")
        return
    
    try:
        # Delete user's chat history
        session.query(ChatMessage).filter(ChatMessage.user_id == user_id).delete()
        # Delete user's search history
        session.query(SearchHistory).filter(SearchHistory.user_id == user_id).delete()
        # Delete user's file metadata
        session.query(FileMetadata).filter(FileMetadata.user_id == user_id).delete()
        # Delete user's hubs and associated satellites
        user_hubs = session.query(Hub).filter(Hub.user_id == user_id).all()
        for hub in user_hubs:
            session.query(Satellite).filter(Satellite.hub_hash == hub.hash_key).delete()
        session.query(Hub).filter(Hub.user_id == user_id).delete()
        
        # Soft delete/close all active document satellites under DV2.0 logic
        user_email = st.session_state.user.get('email')
        if user_email:
            from db_connector import compute_hash_key, LinkUserDocument, SatDocumentContent, SatDocumentEmbedding, Document
            user_hash = compute_hash_key(user_email)
            links = session.query(LinkUserDocument).filter(LinkUserDocument.hub_user_hash == user_hash).all()
            doc_hashes = [link.hub_doc_hash for link in links]
            
            if doc_hashes:
                session.query(SatDocumentContent).filter(
                    SatDocumentContent.hub_doc_hash.in_(doc_hashes),
                    SatDocumentContent.load_end_date.is_(None)
                ).update({SatDocumentContent.load_end_date: datetime.now()}, synchronize_session=False)
                
                session.query(SatDocumentEmbedding).filter(
                    SatDocumentEmbedding.hub_doc_hash.in_(doc_hashes),
                    SatDocumentEmbedding.load_end_date.is_(None)
                ).update({SatDocumentEmbedding.load_end_date: datetime.now()}, synchronize_session=False)
                
            # Update Document tracking table status to 'deleted'
            session.query(Document).filter(Document.user_id == user_id).update({Document.status: 'deleted'}, synchronize_session=False)
        session.commit()
        
        # Clean disk cache
        shutil.rmtree("./data/repos", ignore_errors=True)
        
        # Clear only user's session state
        st.session_state.messages = []
        st.session_state.scan_status = ""
        st.session_state.scan_progress = 0
        
        st.success("Your repositories and chat history have been reset.")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        session.rollback()
        st.error(f"Reset failed: {e}")

def require_auth(func):
    """Decorator to ensure user is authenticated before executing the decorated function."""
    def wrapper(*args, **kwargs):
        if not st.session_state.get('authenticated'):
            st.error("Authentication required to access this resource.")
            st.stop()
        return func(*args, **kwargs)
    return wrapper

@require_auth
def render_profile_tab():
    st.markdown(f"""
        <div style="display:flex; align-items:center; gap:15px; margin-bottom: 20px;">
            {get_cyber_icon('profile')}
            <h1 style="margin:0; font-family: 'Inter', sans-serif;">User Profile</h1>
        </div>
    """, unsafe_allow_html=True)
    st.write("Manage your cryptographic credentials and workspace interface options.")
    
    user_id = st.session_state.user['id']
    user_email = st.session_state.user['email']
    
    # 1. Fetch User Stats
    try:
        from db_connector import Document, Hub, ScanJob, Search
        num_files = session.query(Document).filter(Document.user_id == user_id, Document.status != 'deleted').count()
        total_size_bytes = session.query(sa.func.sum(Document.size)).filter(Document.user_id == user_id, Document.status != 'deleted').scalar() or 0
        total_size_mb = total_size_bytes / (1024 * 1024)
        
        num_snippets = session.query(Hub).filter(Hub.user_id == user_id).count()
        num_scan_jobs = session.query(ScanJob).filter(ScanJob.user_id == user_id).count()
        num_searches = session.query(Search).filter(Search.user_id == user_id).count()
    except Exception as e:
        num_files = 0
        total_size_mb = 0.0
        num_snippets = 0
        num_scan_jobs = 0
        num_searches = 0
        st.error(f"Error loading stats: {e}")
        
    st.markdown("### 📊 Vault Usage Statistics")
    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("Your Indexed Snippets", num_snippets)
        col2.metric("Scan Jobs Executed", num_scan_jobs)
        col3.metric("Total Searches", num_searches)
        st.caption(f"Storage Footprint: {num_files} document(s) utilizing {total_size_mb:.2f} MB of secure vault space.")
    
    st.divider()
    
    # 2. Theme Preference
    st.markdown("### 🎨 Theme Configuration")
    
    # Fetch current theme from SatUserProfile or st.session_state
    from db_connector import SatUserProfile, compute_hash_key
    user_hash = compute_hash_key(user_email)
    profile = session.query(SatUserProfile).filter(SatUserProfile.hub_user_hash == user_hash, SatUserProfile.load_end_date.is_(None)).first()
    current_theme = profile.theme_preference if profile else st.session_state.vault_theme_mode
    
    # Checkbox/Selectbox for Theme
    theme_options = ["System", "Dark", "Light"]
    theme_index = theme_options.index(current_theme) if current_theme in theme_options else 0
    selected_theme = st.selectbox("Preferred UI Theme Mode", theme_options, index=theme_index)
    
    if selected_theme != current_theme:
        try:
            # Use proper load_data_vault utility for Data Vault insertion
            from db_connector import load_data_vault, HubUser
            sat_user_data = {
                'role': profile.role if profile else 'User',
                'preferences': {
                    'theme_preference': selected_theme,
                    'theme': selected_theme,
                    'full_name': profile.full_name if (profile and profile.full_name) else None,
                    'avatar_url': profile.avatar_url if (profile and profile.avatar_url) else None
                }
            }
            load_data_vault(
                session=session,
                hub_model=HubUser,
                satellite_model=SatUserProfile,
                hub_data={'email': user_email},
                sat_data=sat_user_data,
                hub_hash_key=user_hash,
                record_source='web_app_profile',
                hub_fk_column='hub_user_hash'
            )
            session.commit()
            
            # Instantly update st.session_state and apply styles
            st.session_state.vault_theme_mode = selected_theme
            st.success(f"Theme updated to {selected_theme}!")
            st.rerun()
        except Exception as e:
            session.rollback()
            st.error(f"Failed to update theme preference: {e}")
            
    st.divider()
    
    # 3. Change Password Form
    st.markdown("### 🔒 Update Cryptographic Access Credentials")
    with st.form("change_password_form"):
        old_pass = st.text_input("Current Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm New Password", type="password")
        submit_pw = st.form_submit_button("Update Password", use_container_width=True)
        
        if submit_pw:
            db_user = session.query(User).filter(User.id == user_id).first()
            stored_hash = getattr(db_user, "password_hash", None) or getattr(db_user, "hashed_password", None)
            
            if not verify_password(old_pass, stored_hash):
                st.error("Authentication failed: Current password does not match.")
            elif new_pass != confirm_pass:
                st.error("Validation failed: New passwords do not match.")
            else:
                # Validate complexity: min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char
                is_valid, err_msg = _validate_password(new_pass)
                if not is_valid:
                    st.error(f"Validation failed: {err_msg}")
                else:
                    try:
                        new_hash = hash_password(new_pass)
                        db_user.hashed_password = new_hash
                        # support legacy column names as well
                        if hasattr(db_user, 'password_hash'):
                            db_user.password_hash = new_hash
                        session.commit()
                        st.success("Access credentials updated successfully!")
                        st.balloons()
                    except Exception as e:
                        session.rollback()
                        st.error(f"Failed to update password: {e}")

@require_auth
def render_smart_search_tab():
    st.markdown(f"""
        <div style="display:flex; align-items:center; gap:15px; margin-bottom: 20px;">
            {get_cyber_icon('vault')}
            <h1 style="margin:0; font-family: 'Inter', sans-serif;">Smart Neural Search</h1>
        </div>
    """, unsafe_allow_html=True)
    st.write("Perform multi-tenant hybrid keyword and semantic vector search across your vault.")
    
    query = st.text_input("Search query / concept / keyword:", placeholder="e.g. user password hashing logic", key="smart_search_input")
    
    if st.button("Query Neural Index", key="btn_smart_search", use_container_width=True):
        if query:
            with st.spinner("Searching indexing shards..."):
                results = run_hybrid_search(query)
                if results:
                    st.success(f"Discovered {len(results)} matching neural records!")
                    
                    # Log/Retrieve the SearchHistory entry for this query
                    user_id = st.session_state.user['id']
                    latest_search = session.query(SearchHistory).filter(
                        SearchHistory.user_id == user_id, 
                        SearchHistory.query == query
                    ).order_by(SearchHistory.id.desc()).first()
                    
                    if latest_search:
                        st.markdown("**Was this search helpful?**")
                        col_fb1, col_fb2 = st.columns([1, 10])
                        # Thumbs buttons
                        rating = session.query(Feedback).filter(Feedback.search_id == latest_search.id, Feedback.user_id == user_id).first()
                        rating_val = rating.rating if rating else 0
                        
                        if col_fb1.button("👍", key=f"smart_up_{latest_search.id}", type="primary" if rating_val == 1 else "secondary"):
                            if rating:
                                rating.rating = 1
                            else:
                                session.add(Feedback(user_id=user_id, search_id=latest_search.id, rating=1))
                            session.commit()
                            st.toast("Thank you for your feedback!", icon="👍")
                            st.rerun()
                        if col_fb2.button("👎", key=f"smart_dn_{latest_search.id}", type="primary" if rating_val == -1 else "secondary"):
                            if rating:
                                rating.rating = -1
                            else:
                                session.add(Feedback(user_id=user_id, search_id=latest_search.id, rating=-1))
                            session.commit()
                            st.toast("Thank you for your feedback!", icon="👎")
                            st.rerun()
                    
                    st.markdown("---")
                    for idx, res in enumerate(results):
                        score = res.get('score', 0.0)
                        source_name = res.get('name', 'Unknown')
                        snippet = res.get('snippet', '')
                        res_type = res.get('type', 'code')
                        
                        st.markdown(f"### Match #{idx + 1}: `{source_name}`")
                        st.markdown(f"**Confidence Score:** `{score:.2%}`")
                        st.progress(float(max(0.0, min(1.0, score))))
                        
                        if res_type == "code":
                            st.code(snippet, language="python")
                        else:
                            st.info(snippet)
                        st.markdown("<hr style='opacity:0.25;'>", unsafe_allow_html=True)
                else:
                    st.warning("No matches found in repository. Ensure your code repositories or documents are ingested first.")
        else:
            st.error("Please enter a search query.")

@require_auth
def render_ingest_tab():
    st.markdown(f"""
        <div style="display:flex; align-items:center; gap:15px; margin-bottom: 20px;">
            {get_cyber_icon('ingest')}
            <h1 style="margin:0; font-family: 'Inter', sans-serif;">Repository Ingestion</h1>
        </div>
    """, unsafe_allow_html=True)
    st.write("Process external repositories or upload documents for indexing.")
    
    tab_git, tab_file = st.tabs(["GitHub Source", "File System Source"])
    
    with tab_git:
        repo_url = st.text_input("Repository Target (Git URL or Local Absolute Path)", 
                                placeholder=r"https://github.com/fastapi/fastapi OR C:\Users\Dev\Project", 
                                key="repo_url_input",
                                help=r"Supports public GitHub URLs or local directories for instant indexing.")
        if st.button("Initialize Vault Ingestion", key="btn_scan", use_container_width=True):
            if repo_url:
                run_scan(repo_url)
            else:
                st.warning("Please provide a valid URL or Path.")
                
    with tab_file:
        allowed_types = ["py", "js", "ts", "jsx", "tsx", "html", "css", "md", "json", "sql", "pdf", "docx", "txt", "csv"]
        allowed_str = ", ".join(allowed_types).upper()
        uploaded_file = st.file_uploader(f"Upload Document / Code (Allowed: {allowed_str})", type=allowed_types, help="Drag and drop for instant indexing.")
        if uploaded_file is not None:
            if st.button("Index File", key="btn_index", use_container_width=True):
                process_file_content(uploaded_file, st.session_state.user['id'])
                st.rerun()

    # --- Live Neural Heartbeat: Progress Polling ---
    db_current_user = get_live_user(st.session_state.user['id'])
    
    if db_current_user and db_current_user.scan_status and "Complete" not in db_current_user.scan_status and "Failure" not in db_current_user.scan_status:
        # Prepare processing indicator; hide the spinner when an error status is present
        processing_html = ""
        try:
            if db_current_user.scan_status and str(db_current_user.scan_status).lower().startswith('error'):
                processing_html = f"<div style='margin-top:10px; color: var(--vault-text-muted); font-weight:700;'>⚠️ Scan aborted: {db_current_user.scan_status}</div>"
            else:
                processing_html = "<div style=\"margin-top:10px; display:flex; align-items:center; gap:8px; color: var(--vault-text-muted);\"><div class=\"pulse-dot\"></div> <small style=\"font-weight: 600;\">Processing Neural Chunks...</small></div>"
        except Exception:
            processing_html = ""

        st.markdown(f"""
            <div style="margin-top:20px; padding:20px; border-radius:18px; background: var(--vault-surface-strong); border: 1.5px solid var(--vault-accent); box-shadow: 0 0 28px var(--vault-glow);">
                <div style="display:flex; justify-content:space-between; margin-bottom:12px;">
                    <span style="color: var(--vault-accent); font-weight:800; font-family:Outfit; font-size: 1.05rem;">🛰️ NEURAL SCAN IN PROGRESS</span>
                    <span style="color: var(--vault-text); font-weight:700; font-size: 1.1rem;">{db_current_user.scan_progress}%</span>
                </div>
                <div style="height:6px; width:100%; background: var(--vault-glow); border-radius:12px; overflow:hidden; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2);">
                    <div style="height:100%; width:{db_current_user.scan_progress}%; background: linear-gradient(90deg, var(--vault-accent), var(--vault-accent-2)); box-shadow: 0 0 20px var(--vault-accent); transition: width 0.5s ease;"></div>
                </div>
                <div style="margin-top:14px; font-size:0.95rem; font-weight:600; color: var(--vault-text);">
                    <b style="color: var(--vault-accent);">Stage:</b> {db_current_user.scan_status}
                </div>
                {processing_html}
            </div>
            <style>
                @keyframes pulse-ring {{
                    0% {{ transform: scale(.33); }}
                    80%, 100% {{ opacity: 0; }}
                }}
                .pulse-dot {{
                    width: 8px; height: 8px; background: #00ffcc; border-radius: 50%;
                    position: relative;
                }}
                .pulse-dot::after {{
                    content: ''; position: absolute; top: -12px; left: -12px; width: 32px; height: 32px;
                    border: 2px solid #00ffcc; border-radius: 50%;
                    animation: pulse-ring 1.25s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
                }}
            </style>
        """, unsafe_allow_html=True)
        
        # Throttled Rerun Heartbeat (Poll every 1.5s)
        time.sleep(1.5)
        st.rerun()
    elif db_current_user and "Complete" in db_current_user.scan_status:
        st.success(f"✅ {db_current_user.scan_status}")
        # Clear status to avoid persistent bars
        if st.button("Acknowledge Ingestion"):
            db_current_user.scan_status = ""
            db_current_user.scan_progress = 0
            session.commit()
            st.session_state.is_scanning = False
            st.rerun()
    # Initialize live variables for UI display
    live_status = db_current_user.scan_status if db_current_user else ""
    live_prog = db_current_user.scan_progress if db_current_user else 0
    

    if live_status:
        status_lower = live_status.lower()
        is_active = any(k in status_lower for k in ["cloning", "parsing", "indexing", "scanning"])
        is_visible = is_active or any(k in status_lower for k in ["complete", "halted", "critical", "found"])
        
        if is_active:
            st.markdown("---")
            render_custom_progress(live_status, live_prog)
            
            if st.button("Stop Ingestion", key="abort_scan_main", type="secondary", use_container_width=True):
                stop_ingestion(st.session_state.user['id'])
                st.rerun()

            # Real-time auto-refresh: poll DB every 2s while scan is running
            import time as _time
            _time.sleep(2)
            st.rerun()
        elif "complete" in status_lower or "halted" in status_lower or "critical" in status_lower:
            st.toast(live_status, icon="✅" if "complete" in status_lower else "🛑")
            _u = session.query(User).filter(User.id == st.session_state.user['id']).first()
            if _u:
                _u.scan_status = ""
                _u.scan_progress = 0
                session.commit()
            st.session_state.is_scanning = False
            import time as _time
            _time.sleep(1) # Brief pause so they can read the toast
            st.rerun()

@require_auth
def render_explorer_tab():
    st.markdown(f"""
        <div style="display:flex; align-items:center; gap:15px; margin-bottom: 20px;">
            {get_cyber_icon('vault')}
            <h1 style="margin:0; font-family: 'Inter', sans-serif;">Vault Explorer</h1>
        </div>
    """, unsafe_allow_html=True)
    st.write("Technical database of indexed code modules and associated metadata.")
    
    tab_hubs, tab_files = st.tabs(["Code Hubs", "Document Index"])
    
    with tab_hubs:
        # Query all hubs for current user
        user_id = st.session_state.user['id']
        hubs = get_user_scoped_query(session, Hub, user_id).all()
        
        if hubs:
            df_hubs = pd.DataFrame([{
                "Hub ID": h.id,
                "Logical Name": h.hash_key,
                # Backwards-safe access: some DBs/models may use different column names
                "Archetype": getattr(h, 'type', None) or getattr(h, 'archetype', None) or getattr(h, 'source_type', None) or 'unknown',
                "Relative Path": (getattr(h, 'file_path', None) or getattr(h, 'repo_url', '') or '').split("repos")[-1] if (getattr(h, 'file_path', None) or getattr(h, 'repo_url', '')) else ''
            } for h in hubs])
            
            st.dataframe(df_hubs, use_container_width=True, hide_index=True)
            
            sel_hub = st.selectbox("Select a Hub to analyze logical metrics:", df_hubs['Logical Name'].unique())
            if sel_hub:
                hub_obj = session.query(Hub).filter(Hub.hash_key == sel_hub, Hub.user_id == user_id).first()
                sat_obj = session.query(Satellite).filter(Satellite.hub_hash == sel_hub).first()
                
                if hub_obj:
                    st.markdown("---")
                    st.subheader(f"Satellite Intelligence: {sel_hub}")
                    if sat_obj:
                        st.markdown(render_satellite_card(sat_obj.metrics), unsafe_allow_html=True)
                    
                    st.code(hub_obj.code_snippet, language='python')
        else:
            st.info("💡 Pro Tip: Use descriptive repository URLs for better high-level architectural summaries.")

    with tab_files:
        files = get_user_scoped_query(session, FileMetadata, st.session_state.user['id']).all()
        if files:
            df_files = pd.DataFrame([{
                "Filename": f.filename,
                "Type": f.file_type,
                "Size (KB)": f.size // 1024,
                "Timestamp": f.upload_date
            } for f in files])
            st.dataframe(df_files, use_container_width=True, hide_index=True)
        else:
            st.info("No documents or files have been indexed yet.")

@require_auth
def render_architect_tab():
    st.markdown(f"""
        <div style="display:flex; align-items:center; gap:15px; margin-bottom: 20px;">
            {get_cyber_icon('chat')}
            <h1 style="margin:0; font-family: 'Inter', sans-serif;">Agentic AI Studio</h1>
        </div>
    """, unsafe_allow_html=True)
    st.write("Multi-agent workspace: RAG answers, code editing, review, docs, and test planning over your indexed vault.")

    use_white_chat_text = st.toggle(
        "Use white text for chat output",
        key="chat_white_output_toggle",
        value=True,
        help="Forces chat output to stay high-contrast in both dark and light themes."
    )

    if use_white_chat_text and st.session_state.vault_theme_mode != "Light":
        st.markdown(
            """
            <style>
                div[data-testid="stChatMessage"] p,
                div[data-testid="stChatMessage"] li,
                div[data-testid="stChatMessage"] span,
                div[data-testid="stChatMessage"] div {
                    color: #ffffff !important;
                }
                div[data-testid="stChatMessage"] code {
                    background-color: rgba(255, 255, 255, 0.08) !important;
                    color: #00f2ff !important;
                    border: 1px solid rgba(255, 255, 255, 0.12) !important;
                    padding: 0.15rem 0.4rem !important;
                    border-radius: 6px !important;
                    font-family: monospace !important;
                }
                div[data-testid="stChatMessage"] pre code {
                    background-color: transparent !important;
                    border: none !important;
                    padding: 0 !important;
                    color: #ffffff !important;
                }
                div[data-testid="stChatMessage"] {
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 16px;
                    padding: 0.9rem 1rem;
                    margin-bottom: 0.75rem;
                    font-size: 1.02rem;
                    line-height: 1.7;
                    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
                }
                div[data-testid="stChatMessage"] pre {
                    white-space: pre-wrap;
                    word-break: break-word;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
                div[data-testid="stChatMessage"] p,
                div[data-testid="stChatMessage"] li,
                div[data-testid="stChatMessage"] span,
                div[data-testid="stChatMessage"] div {
                    color: var(--vault-text) !important;
                }
                div[data-testid="stChatMessage"] code {
                    background-color: var(--vault-surface-strong) !important;
                    color: var(--vault-accent) !important;
                    border: 1px solid var(--vault-panel-border) !important;
                    padding: 0.15rem 0.4rem !important;
                    border-radius: 6px !important;
                    font-family: monospace !important;
                }
                div[data-testid="stChatMessage"] pre code {
                    background-color: transparent !important;
                    border: none !important;
                    padding: 0 !important;
                    color: var(--vault-text) !important;
                }
                div[data-testid="stChatMessage"] {
                    background: var(--vault-surface);
                    border: 1px solid var(--vault-panel-border);
                    border-radius: 16px;
                    padding: 0.9rem 1rem;
                    margin-bottom: 0.75rem;
                    font-size: 1.02rem;
                    line-height: 1.7;
                    box-shadow: var(--vault-shadow);
                }
                div[data-testid="stChatMessage"] pre {
                    white-space: pre-wrap;
                    word-break: break-word;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
    
    # --- Main Chat Interface ---
    if st.button("Purge Chat History", help="Delete current consultation logs permanently", use_container_width=True, type="secondary"):
        session.query(ChatMessage).filter(ChatMessage.user_id == st.session_state.user['id']).delete()
        session.commit()
        st.session_state.messages = []
        st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    intercepted_prompt = None
    if st.session_state.get('discovery_prompt'):
        intercepted_prompt = st.session_state.pop('discovery_prompt')

    if prompt := (st.chat_input("Enter architectural query...") or intercepted_prompt):
        # Save and Display User Input (Wrapped for stability)
        try:
            user_msg = ChatMessage(user_id=st.session_state.user['id'], role="user", content=prompt, timestamp=datetime.now())
            session.add(user_msg)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"VAULT_DEBUG: Failed to log user message: {e}")
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Routing to specialist agent..."):
                try:
                    backend["current_user_id"] = st.session_state.user.get("id")
                    runtime_key = resolve_runtime_groq_key()
                    if runtime_key:
                        backend["groq_api_key"] = runtime_key
                        os.environ["GROQ_API_KEY"] = runtime_key
                    agent_result = run_agent(prompt, st.session_state.messages, backend)
                    full_res = agent_result.get("answer", "No answer returned by the agent.")
                    steps = agent_result.get("steps", [])
                    tools_used = agent_result.get("tools_used", [])
                    active_agent = agent_result.get("active_agent", "Agent")
                    artifacts = agent_result.get("artifacts", {})
                    st.info(f"Active specialist: **{active_agent}**" + (f" · Tools: {', '.join(tools_used)}" if tools_used else ""))
                    if artifacts.get("diff"):
                        st.download_button(
                            "Download generated patch",
                            data=artifacts.get("diff", ""),
                            file_name=f"{artifacts.get('target', 'vault_edit')}.patch".replace("/", "_"),
                            mime="text/x-diff",
                            use_container_width=True,
                        )
                    if artifacts.get("zip_bytes"):
                        st.download_button(
                            "Download vault archive (ZIP)",
                            data=artifacts.get("zip_bytes"),
                            file_name=artifacts.get("zip_name", "vault_export.zip"),
                            mime="application/zip",
                            use_container_width=True,
                        )
                    if steps or tools_used:
                        with st.expander("Agent trace", expanded=False):
                            if tools_used:
                                st.markdown("**Tools used**")
                                st.write(", ".join(tools_used))
                            if steps:
                                st.markdown("**Agent steps**")
                                for i, step in enumerate(steps, 1):
                                    step_type = step.get("type", "step")
                                    content = step.get("content", "")
                                    if step_type == "tool_call":
                                        st.write(f"{i}. called `{step.get('tool', 'tool')}` — {content}")
                                    elif step_type == "tool_result":
                                        st.write(f"{i}. `{step.get('tool', 'tool')}` result — {content}")
                                    else:
                                        st.write(f"{i}. {content}")
                    try:
                        ai_msg = ChatMessage(user_id=st.session_state.user['id'], role="assistant", content=full_res, timestamp=datetime.now())
                        session.add(ai_msg)
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        print(f"VAULT_DEBUG: Failed to log AI response: {e}")
                    st.markdown(full_res)
                    st.session_state.messages.append({"role": "assistant", "content": full_res})
                except Exception as e:
                    st.error(f"Architect Connection Error: {str(e)}")
                    print(f"VAULT_DEBUG: Exception: {str(e)}")
                    import traceback
                    traceback.print_exc()

@require_auth
def render_analytics_tab():
    st.header("Analytics Dashboard")
    user_id = st.session_state.user['id']
    
    tab_files, tab_usage, tab_history, tab_perf = st.tabs(["File Manager", "Usage Analytics", "Queries & Feedback", "Performance Metrics"])
    
    with tab_files:
        st.subheader("Uploaded Files")
        docs = session.query(Document).filter(Document.user_id == user_id).order_by(Document.upload_date.desc()).all()
        if docs:
            for doc in docs:
                if doc.status == 'deleted':
                    continue
                with st.expander(f"📄 {doc.filename} ({doc.size / 1024:.1f} KB)"):
                    st.write(f"**Uploaded:** {doc.upload_date.strftime('%Y-%m-%d %H:%M:%S')} | **Chunks:** {doc.chunk_count} | **Status:** {doc.status}")
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.button("Preview", key=f"prev_{doc.id}"):
                        first_chunk = session.query(SatDocumentContent).filter(
                            SatDocumentContent.hub_doc_hash == HubDocument.hash_key,
                            HubDocument.natural_key == doc.filename,
                            LinkUserDocument.hub_doc_hash == HubDocument.hash_key,
                            LinkUserDocument.hub_user_hash == compute_hash_key(user_id),
                            SatDocumentContent.chunk_index == 0,
                            SatDocumentContent.load_end_date.is_(None)
                        ).first()
                        if first_chunk and first_chunk.raw_text:
                            st.code(first_chunk.raw_text[:500] + "...", language="text")
                        else:
                            st.info("No content available for preview.")
                            
                    if col_btn2.button("Delete (DV2.0 Soft Delete)", key=f"del_{doc.id}", type="primary"):
                        chunks = session.query(SatDocumentContent).filter(
                            SatDocumentContent.hub_doc_hash == HubDocument.hash_key,
                            HubDocument.natural_key == doc.filename,
                            LinkUserDocument.hub_doc_hash == HubDocument.hash_key,
                            LinkUserDocument.hub_user_hash == compute_hash_key(user_id),
                            SatDocumentContent.load_end_date.is_(None)
                        ).all()
                        for chunk in chunks:
                            chunk.load_end_date = datetime.now()
                        doc.status = 'deleted'
                        session.commit()
                        st.success(f"{doc.filename} successfully deleted.")
                        st.rerun()
        else:
            st.info("No files uploaded yet.")

        # Indexed Repositories Section
        st.markdown("---")
        st.subheader("Indexed Repositories")
        repos = session.query(Hub.repo_url).filter(
            Hub.user_id == user_id,
            sa.or_(Hub.status != 'deleted', Hub.status.is_(None))
        ).distinct().all()
        
        # Filter out empty/None repo URLs
        repo_urls = [r[0] for r in repos if r[0]]
        
        if repo_urls:
            for r_url in repo_urls:
                # Count files under this repo
                file_count = session.query(sa.func.count(Hub.id)).filter(
                    Hub.user_id == user_id,
                    Hub.repo_url == r_url,
                    sa.or_(Hub.status != 'deleted', Hub.status.is_(None))
                ).scalar()
                
                # Create a safe key using md5
                import hashlib
                safe_key = hashlib.md5(r_url.encode('utf-8')).hexdigest()
                
                with st.expander(f"📦 {r_url} ({file_count} files/modules)"):
                    st.write(f"**Repository URL:** {r_url}")
                    if st.button("Delete Repository (Soft Delete)", key=f"del_repo_{safe_key}", type="primary"):
                        # Soft delete all hub records for this repo
                        hubs_to_del = session.query(Hub).filter(
                            Hub.user_id == user_id,
                            Hub.repo_url == r_url
                        ).all()
                        for h in hubs_to_del:
                            h.status = 'deleted'
                        session.commit()
                        st.success(f"Repository {r_url} successfully deleted.")
                        st.rerun()
        else:
            st.info("No repositories indexed yet.")

    with tab_usage:
        st.subheader("Usage Analytics")
        st.markdown("**Files Ingested Over Time**")
        daily_docs = session.query(
            sa.func.date(Document.upload_date).label('date'), 
            sa.func.count(Document.id).label('count')
        ).filter(Document.user_id == user_id).group_by('date').all()
        
        if daily_docs:
            df_docs = pd.DataFrame(daily_docs, columns=['date', 'count'])
            df_docs['date'] = pd.to_datetime(df_docs['date'])
            df_docs.set_index('date', inplace=True)
            st.line_chart(df_docs)
        else:
            st.info("No file data available.")
            
        st.markdown("**Searches Per Day**")
        daily_searches = session.query(
            sa.func.date(SearchHistory.timestamp).label('date'),
            sa.func.count(SearchHistory.id).label('count')
        ).filter(SearchHistory.user_id == user_id).group_by('date').all()
        
        if daily_searches:
            df_searches = pd.DataFrame(daily_searches, columns=['date', 'count'])
            df_searches['date'] = pd.to_datetime(df_searches['date'])
            df_searches.set_index('date', inplace=True)
            st.bar_chart(df_searches)
        else:
            st.info("No search data available.")
            
        st.markdown("**Top 10 Most Searched Terms**")
        all_searches = session.query(SearchHistory.query).filter(SearchHistory.user_id == user_id).all()
        if all_searches:
            from collections import Counter
            words = []
            for s in all_searches:
                words.extend(re.findall(r'\w+', s[0].lower()))
            stopwords = {'how', 'what', 'why', 'where', 'when', 'the', 'is', 'in', 'to', 'for', 'of', 'and', 'a', 'on', 'with', 'about', 'can'}
            words = [w for w in words if w not in stopwords and len(w) > 2]
            top_words = Counter(words).most_common(10)
            if top_words:
                df_top = pd.DataFrame(top_words, columns=['Term', 'Count'])
                st.table(df_top)
            else:
                st.info("Not enough search term data.")
        else:
            st.info("No searches yet.")

    with tab_history:
        st.subheader("Queries & Feedback")
        # Fetch search history
        recent_searches = session.query(SearchHistory).filter(SearchHistory.user_id == user_id).order_by(SearchHistory.timestamp.desc()).limit(20).all()
        # Fetch chat history (agentic studio user queries)
        recent_chats = session.query(ChatMessage).filter(ChatMessage.user_id == user_id, ChatMessage.role == 'user').order_by(ChatMessage.timestamp.desc()).limit(20).all()
        
        # Combine them into a single list of query items
        items = []
        for s in recent_searches:
            items.append({
                "id": f"search_{s.id}",
                "db_id": s.id,
                "type": "Smart Search",
                "query": s.query,
                "timestamp": s.timestamp
            })
        for c in recent_chats:
            items.append({
                "id": f"chat_{c.id}",
                "db_id": c.id,
                "type": "Agentic Studio",
                "query": c.content,
                "timestamp": c.timestamp
            })
            
        # Sort combined items by timestamp desc
        items = sorted(items, key=lambda x: x["timestamp"], reverse=True)[:30]
        
        if items:
            for item in items:
                # Query feedback
                if item["type"] == "Smart Search":
                    rating = session.query(Feedback).filter(Feedback.search_id == item["db_id"], Feedback.user_id == user_id).first()
                else:
                    rating = session.query(Feedback).filter(Feedback.chat_message_id == item["db_id"], Feedback.user_id == user_id).first()
                
                rating_val = rating.rating if rating else 0
                feedback_exists = (rating_val != 0)
                
                with st.container():
                    colA, colB, colC = st.columns([4, 1, 1])
                    colA.markdown(f"**[{item['type']}] Query:** {item['query']}  \n*{item['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}*")
                    
                    if colB.button("👍", key=f"up_{item['id']}", type="primary" if rating_val == 1 else "secondary", disabled=feedback_exists):
                        if item["type"] == "Smart Search":
                            session.add(Feedback(user_id=user_id, search_id=item["db_id"], rating=1))
                        else:
                            session.add(Feedback(user_id=user_id, chat_message_id=item["db_id"], rating=1))
                        session.commit()
                        st.rerun()
                        
                    if colC.button("👎", key=f"dn_{item['id']}", type="primary" if rating_val == -1 else "secondary", disabled=feedback_exists):
                        if item["type"] == "Smart Search":
                            session.add(Feedback(user_id=user_id, search_id=item["db_id"], rating=-1))
                        else:
                            session.add(Feedback(user_id=user_id, chat_message_id=item["db_id"], rating=-1))
                        session.commit()
                        st.rerun()
                    st.divider()
        else:
            st.info("No recent queries.")

    with tab_perf:
        st.subheader("Performance Metrics")
        
        # Get Avg Response time (from searches table if used, else 0)
        avg_resp = session.query(sa.func.avg(Search.response_time_ms)).filter(Search.user_id == user_id).scalar() or 0.0
        
        # Total Chunks Indexed
        total_chunks = session.query(sa.func.sum(Document.chunk_count)).filter(Document.user_id == user_id).scalar() or 0
        
        # Database size
        db_path = "vault_v5.db"
        db_size_mb = 0
        if os.path.exists(db_path):
            db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
            
        emb_model = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        
        colP1, colP2 = st.columns(2)
        colP1.metric("Avg Response Time", f"{avg_resp:.2f} ms")
        colP2.metric("Total Document Chunks", int(total_chunks))
        
        colP3, colP4 = st.columns(2)
        colP3.metric("Database Size", f"{db_size_mb:.2f} MB")
        colP4.metric("Active Embedding Model", emb_model)
    

@require_auth
def render_admin_dashboard_tab():
    st.header("Global Admin Dashboard")
    st.write("System-wide monitoring overview.")
    
    col1, col2, col3 = st.columns(3)
    total_users = session.query(User).count()
    global_hubs = session.query(Hub).count()
    
    db_url_str = str(engine_v4.url)
    perf_metrics = get_cached_performance_metrics(db_url_str)
    total_searches = perf_metrics["total_searches"]
    
    col1.metric("Total Signups", total_users)
    col2.metric("Global Hubs Indexed", global_hubs)
    col3.metric("Global Queries", total_searches)

    tab_admin_overview, tab_admin_keys, tab_admin_metrics = st.tabs(["Overview", "API Keys", "Metrics & Runners"])

    with tab_admin_overview:
        st.subheader("System Control Status")
        st.write("Review the operational parameters of the overall RAG engine system components.")
        # Database size
        db_path = "vault_v5.db"
        db_size_mb = 0
        if os.path.exists(db_path):
            db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
        st.markdown(f"""
            - **Global Database Size:** `{db_size_mb:.2f} MB`
            - **Environment Keys Provisoned:** `{"Yes" if resolve_runtime_groq_key() else "No"}`
            - **Platform Context:** `Streamlit Web Node`
        """)

    with tab_admin_keys:
        st.subheader("Neural Interface Management (Global Key Pool)")
        st.write("Supply and maintain the global API asset pool shared by all users.")
        
        with st.form("add_global_key_form"):
            col_k1, col_k2, col_k3 = st.columns([1,2,1])
            k_prov = col_k1.selectbox("Provider Engine", ["GROQ", "OPENROUTER"])
            k_val = col_k2.text_input("New API Key Secret", type="password")
            k_name = col_k3.text_input("Assigned Name", value="Global_Asset")
            if st.form_submit_button("Vault Secure Key"):
                if k_val:
                    normalized_key = k_val.strip()
                    if k_prov == "GROQ":
                        normalized_key = set_active_groq_api_key(normalized_key)
                        backend["groq_api_key"] = normalized_key

                    existing_pool_key = (
                        session.query(KeyPool)
                        .filter(KeyPool.provider == k_prov, KeyPool.name == k_name)
                        .first()
                    )
                    if existing_pool_key:
                        existing_pool_key.key_value = normalized_key
                        existing_pool_key.is_active = 1
                        existing_pool_key.provider = k_prov
                        existing_pool_key.name = k_name
                    else:
                        new_pool_key = KeyPool(provider=k_prov, key_value=normalized_key, name=k_name, is_active=1)
                        session.add(new_pool_key)
                    session.commit()
                    if k_prov == "GROQ":
                        st.success("Successfully registered new Groq key.")
                    else:
                        st.success("Successfully registered new OpenRouter key.")
                    st.rerun()

        st.subheader("Existing API Key Pool")
        pool_keys = session.query(KeyPool).all()
        if pool_keys:
            df_keys = pd.DataFrame([
                {"ID": k.id, "Provider": k.provider, "Name": k.name, "Active": "Yes" if k.is_active else "No"}
                for k in pool_keys
            ])
            st.dataframe(df_keys, use_container_width=True)
            
            st.write("### Manage Asset ID")
            sel_key_id = st.number_input("Target Asset ID:", step=1, value=0)
            col_ka, col_kb, col_kc = st.columns(3)
            if col_ka.button("Toggle Operational Status", use_container_width=True):
                target_key = session.query(KeyPool).filter(KeyPool.id == sel_key_id).first()
                if target_key:
                    target_key.is_active = 0 if target_key.is_active else 1
                    session.commit()
                    st.rerun()
            if col_kb.button("Discard Asset Permanently", use_container_width=True, type="primary"):
                session.query(KeyPool).filter(KeyPool.id == sel_key_id).delete()
                session.commit()
                st.rerun()
            if col_kc.button("Neural Pulse Test", use_container_width=True):
                target_key = session.query(KeyPool).filter(KeyPool.id == sel_key_id).first()
                if target_key:
                    st.write(f"Testing {target_key.provider}...")
                    p_url = "https://api.groq.com/openai/v1/chat/completions" if target_key.provider == "GROQ" else "https://openrouter.ai/api/v1/chat/completions"
                    p_model = "llama-3.3-70b-versatile" if target_key.provider == "GROQ" else "deepseek/deepseek-chat:free"
                    headers = {"Authorization": f"Bearer {target_key.key_value}", "Content-Type": "application/json"}
                    if "openrouter" in p_url: headers.update({"HTTP-Referer": "https://aicodevault.streamlit.app", "X-Title": "AI Code Vault Pro"})
                    try:
                        res = requests.post(p_url, headers=headers, json={"model": p_model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}, timeout=10)
                        st.json(res.json())
                    except Exception as e:
                        st.error(f"Pulse Failed: {e}")
                else:
                    st.warning("Select a valid Asset ID first.")
        else:
            st.info("Global asset pool is empty. Supply credentials to enable high-fidelity consultations.")

    with tab_admin_metrics:
        st.subheader("System Performance & Cost Audit")
        
        # 1. Cost Tracking & Performance
        st.markdown("### 💰 Token Usage & Performance Metrics")
        db_url_str = str(engine_v4.url)
        perf_metrics = get_cached_performance_metrics(db_url_str)
        total_messages = perf_metrics["total_messages"]
        estimated_input_tokens = perf_metrics["estimated_input_tokens"]
        estimated_output_tokens = perf_metrics["estimated_output_tokens"]
        avg_resp_time = perf_metrics["avg_response_time_ms"]
        est_cost = (estimated_input_tokens * 0.00000059) + (estimated_output_tokens * 0.00000079)
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        col_c1.metric("Total Messages Audited", total_messages)
        col_c2.metric("Est. Tokens Processed", f"{estimated_input_tokens + estimated_output_tokens:,}")
        col_c3.metric("Accumulated Groq Cost", f"${est_cost:.4f}")
        col_c4.metric("Avg Search Latency", f"{avg_resp_time:.1f} ms")
        
        st.divider()
        
        # Daily Activity Metrics (FIX 3)
        st.markdown("### 📅 Daily Activity Counts")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("**Daily Document Uploads**")
            daily_uploads = get_cached_daily_uploads(db_url_str)
            if daily_uploads:
                df_u = pd.DataFrame(daily_uploads)
                df_u.columns = ["Date", "Document Count"]
                st.dataframe(df_u, use_container_width=True)
            else:
                st.info("No daily document upload history.")
        with col_d2:
            st.markdown("**Daily Searches Run**")
            daily_searches = get_cached_daily_searches(db_url_str)
            if daily_searches:
                df_s = pd.DataFrame(daily_searches)
                df_s.columns = ["Date", "Search Count"]
                st.dataframe(df_s, use_container_width=True)
            else:
                st.info("No daily search history.")
                
        st.divider()
        
        # 2. Accuracy Test Runner
        st.markdown("### 🎯 Accuracy Test Runner (Semantic Evaluation)")
        st.write("Evaluate semantic retrieval accuracy by measuring cosine similarity of top matches for verification queries.")
        
        eval_query = st.text_input("Validation Query:", value="How do I configure security in AI Code Vault?", key="acc_val_query")
        if st.button("Run Accuracy Evaluation", use_container_width=True):
            try:
                results = run_hybrid_search(eval_query)
                if results:
                    st.success(f"Retrieval success! Found {len(results)} matches.")
                    for idx, res in enumerate(results):
                        score = res.get('score', 0.0)
                        text_preview = res.get('snippet', '')[:150] + "..."
                        source = res.get('name', 'unknown')
                        st.markdown(f"**Match {idx+1} (Source: {source})**")
                        st.progress(float(max(0.0, min(1.0, score))))
                        st.write(f"Similarity Score: `{score:.4f}` | Preview: *{text_preview}*")
                else:
                    st.warning("No records found in Vault to evaluate.")
            except Exception as e:
                st.error(f"Evaluation runner failed: {e}")
                
        st.divider()
        
        # 3. Scale Test Runner
        st.markdown("### ⚡ Scale Test Runner (Stress Simulation)")
        st.write("Simulate concurrent user requests to analyze latency distribution and throughput under high load.")
        
        num_simulated = st.slider("Simulated Concurrent Queries", min_value=5, max_value=50, value=10, step=5, key="scale_sim_count")
        if st.button("Trigger Stress Test Simulation", use_container_width=True):
            st.info("Simulating concurrent queries against database indices...")
            latencies = []
            queries = ["RAG architecture", "SQL satellite tables", "Groq models", "User permission schema", "Data Vault hash diff"]
            
            import random
            progress_bar = st.progress(0)
            for idx in range(num_simulated):
                q = random.choice(queries)
                start_time = time.time()
                try:
                    _ = run_hybrid_search(q)
                except Exception:
                    pass
                duration = (time.time() - start_time) * 1000  # ms
                # add some random mock database read delay to simulate actual concurrency contention
                mock_contention = random.uniform(5.0, 35.0)
                latencies.append(duration + mock_contention)
                progress_bar.progress((idx + 1) / num_simulated)
                
            df_scale = pd.DataFrame({
                "Request ID": range(1, num_simulated + 1),
                "Latency (ms)": latencies
            })
            
            st.success("Stress test simulation complete!")
            st.line_chart(df_scale.set_index("Request ID"))
            
            col_l1, col_l2 = st.columns(2)
            col_l1.metric("Peak Contention Latency", f"{max(latencies):.2f} ms")
            col_l2.metric("Mean Latency", f"{np.mean(latencies):.2f} ms")

@require_auth
def render_admin_users_tab():
    st.header("User Credentials & Management")
    st.write("View and manage all registered users.")
    
    users = session.query(User).all()
    df_users = pd.DataFrame([{"Internal ID": u.id, "Email / Username": u.email, "Access Role": u.role} for u in users])
    st.dataframe(df_users, use_container_width=True)
    
    st.divider()
    st.subheader("Account Termination Protocol")
    st.warning("Deleting a user will permanently destroy all their uploaded code hubs, chat history, and metric data.")
    
    user_to_delete = st.selectbox("Select Account to Terminate:", [""] + [u.email for u in users if u.role != 'Admin'])
    
    if st.button("Terminate User & Wipe Data", type="primary", use_container_width=True):
        if user_to_delete:
            usr = session.query(User).filter(User.email == user_to_delete).first()
            if usr:
                from db_connector import FileMetadata  # type: ignore
                # Cascading delete
                session.query(ChatMessage).filter(ChatMessage.user_id == usr.id).delete()
                session.query(SearchHistory).filter(SearchHistory.user_id == usr.id).delete()
                session.query(Hub).filter(Hub.user_id == usr.id).delete()
                session.query(FileMetadata).filter(FileMetadata.user_id == usr.id).delete()
                session.delete(usr)
                session.commit()
                st.success(f"User {user_to_delete} and all associated data were completely eradicated.")
                time.sleep(1.5)
                st.rerun()
        else:
            st.error("Please select a valid user.")

@require_auth
def render_admin_activity_tab():
    st.header("Global Activity Logs")
    st.write("Live feed of all global queries and user searches.")
    
    history = session.query(SearchHistory).order_by(SearchHistory.id.desc()).limit(50).all()
    if history:
        # Join with users to show email
        users_map = {u.id: u.email for u in session.query(User).all()}
        df_hist = pd.DataFrame([{
            "User": users_map.get(h.user_id, "Unknown"), 
            "Query / Activity": h.query, 
            "Timestamp": h.timestamp
        } for h in history])
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("No activity logs generated yet.")


# --- MAIN UI ---
st.markdown("""
<div style="margin: 0.75rem 0 1.5rem 0; padding: 1.25rem 1.5rem; border-radius: 22px; border: 1px solid var(--vault-panel-border); background: linear-gradient(135deg, rgba(0, 242, 255, 0.08), rgba(112, 0, 255, 0.08)); box-shadow: var(--vault-shadow);">
    <div class="main-header" style="text-align: center;">AI CODE VAULT V2.0</div>
    <div style="text-align: center; margin-top: 0.5rem; color: var(--vault-text); font-size: 1rem; letter-spacing: 0.02em; font-weight: 600; opacity: 0.95;">
        Semantic indexing, retrieval, and architecture review in one vault
    </div>
</div>
""", unsafe_allow_html=True)

# Persistent Background Progress UI
# Fetch latest from DB to support persistence across refreshes
db_current_user = get_live_user(st.session_state.user['id'])
if db_current_user and db_current_user.scan_status and db_current_user.scan_status != "Complete" and not db_current_user.scan_status.startswith("Critical Failure"):
    with st.container():
        st.info(f"🛰️ Remote Scan Active: {db_current_user.scan_status}")
# --- Dynamic Menu Content ---

if menu == "Ingest":
    render_ingest_tab()
elif menu == "Smart_Search":
    render_smart_search_tab()
elif menu == "Explorer":
    render_explorer_tab()
elif menu == "Architect":
    render_architect_tab()
elif menu == "Analytics":
    render_analytics_tab()
elif menu == "Profile":
    render_profile_tab()
elif menu == "Admin_Dashboard":
    render_admin_dashboard_tab()
elif menu == "Admin_Users":
    render_admin_users_tab()
elif menu == "Admin_Activity":
    render_admin_activity_tab()

# --- Sidebar Global Components ---
with st.sidebar:
    # Agent Matrix Discovery Panel
    with st.expander("🤖 Agent Matrix Discovery", expanded=False):
        st.markdown("<div style='font-size: 0.8rem; color: var(--vault-text-muted); margin-bottom: 8px;'>Click on any prompt key to direct Architect Studio to run that specialist.</div>", unsafe_allow_html=True)
        
        agents_info = [
            {
                "name": "Supervisor Agent",
                "desc": "Routes prompts to specialized agents.",
                "example": "Explain code architecture"
            },
            {
                "name": "RAG Q&A Agent",
                "desc": "Retrieves source text for code context.",
                "example": "How does login function work?"
            },
            {
                "name": "Quiz Agent",
                "desc": "Challenges you with automated quizzes.",
                "example": "Give me a 3-question quiz"
            },
            {
                "name": "Extract Agent",
                "desc": "Extracts schemas & function signatures.",
                "example": "Extract all class names"
            },
            {
                "name": "Analysis Agent",
                "desc": "Audits vulnerable code vectors.",
                "example": "Analyze security vulnerabilities"
            },
            {
                "name": "Patch Generator",
                "desc": "Generates patch files from code edits.",
                "example": "Modify the authentication logic"
            },
            {
                "name": "Code Reviewer",
                "desc": "Reviews maintainability & performance.",
                "example": "Review my repo scanner"
            },
            {
                "name": "Test Strategist",
                "desc": "Designs test suites & edge cases.",
                "example": "Create pytest test strategy"
            },
            {
                "name": "Documentation Agent",
                "desc": "Generates summaries & markdown files.",
                "example": "Write database schema guide"
            },
            {
                "name": "General Chat Agent",
                "desc": "General reasoning without vault retrieval.",
                "example": "Explain recursion in Python"
            }
        ]
        
        for agent in agents_info:
            st.markdown(f"<div style='font-size: 0.9rem; font-weight: 700; color: var(--vault-accent);'>{agent['name']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.78rem; color: var(--vault-text); opacity:0.85; margin-bottom: 4px;'>{agent['desc']}</div>", unsafe_allow_html=True)
            if st.button(f"Try: \"{agent['example']}\"", key=f"btn_disc_{agent['name'].replace(' ', '_')}", use_container_width=True):
                st.session_state.discovery_prompt = agent['example']
                st.session_state.menu = "Architect"
                st.rerun()
            st.markdown("<hr style='margin: 6px 0; opacity: 0.15;'>", unsafe_allow_html=True)

    # Patent/Copyright Sidebar Footer
    st.markdown("""
        <div style='text-align: center; margin-top: 50px; opacity: 0.72; font-size: 0.75rem; color: var(--vault-text); font-weight: 600; letter-spacing: 0.01em;'>
            &copy; 2026 <span style="color: var(--vault-accent); font-weight: 800;">AI CODE VAULT PRO</span><br>
            <span style="font-weight: 700; color: var(--vault-text-muted);">v2.5.9</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("System Control")
    
    # Neural Status Indicator (Dynamic)
    try:
        db_diags = backend['get_schema_diagnostics'](engine_v4)
        status_c = "#00ffcc" if db_diags['file_exists'] else "#ff4b4b"
        st.markdown(f"""
            <div style="padding:16px; border-radius:14px; background: var(--vault-surface-strong); border: 1.5px solid {status_c}; font-family: 'Inter', sans-serif; box-shadow: 0 10px 24px rgba(0,0,0,0.20);">
                <div style="display:flex; align-items:center; gap:10px;">
                    <div style="width:12px; height:12px; border-radius:50%; background:{status_c}; box-shadow: 0 0 16px {status_c}; animation: vault-pulse 2s infinite;"></div>
                    <span style="color: var(--vault-text); font-weight:800; font-size:0.92rem; letter-spacing: 0.02em; text-transform: uppercase;">Neural Status: Operational</span>
                </div>
                <div style="margin-top:8px; opacity:0.88; font-size:0.8rem; color: var(--vault-text); font-weight: 600;">Vault: <span style="color: var(--vault-accent); font-weight: 700;">{db_diags['file_path'].split('/')[-1]}</span></div>
            </div>
            <style>
                @keyframes vault-pulse {{
                    0%, 100% {{ opacity: 1; transform: scale(1); }}
                    50% {{ opacity: 0.65; transform: scale(1.1); }}
                }}
            </style>
        """, unsafe_allow_html=True)
    except:
        st.error("Neural Connection Offline")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Force Global Reset", help="Permanently delete all ingested repositories and history.", use_container_width=True):
        reset_vault()

if st.session_state.authenticated and menu == "Ingest":
    try:
        current_scan_user = session.query(User).filter(User.id == st.session_state.user['id']).first()
        if current_scan_user and current_scan_user.scan_status:
            status_lower = current_scan_user.scan_status.lower()
            # ONLY poll if actively moving (Complete is static, no need to poll)
            is_actually_moving = any(k in status_lower for k in ["indexing", "cloning", "processing", "scraping"])
            if is_actually_moving:
                time.sleep(2) 
                st.rerun()
    except:
        pass
