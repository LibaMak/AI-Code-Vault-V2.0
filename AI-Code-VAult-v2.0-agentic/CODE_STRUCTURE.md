# AI CODE VAULT 2.0 - Code Structure & Organization

## 📁 Project Structure

```
AI_CODE_VAULT_2.0/
├── streamlit_app.py          # Main application entry point
├── requirements.txt          # Python dependencies
├── .env                       # Environment variables (git-ignored)
├── .env.example              # Template for environment setup
├── Dockerfile                # Container configuration
│
├── backend/                  # Backend modules
│   ├── db_connector.py       # Database models & ORM setup
│   ├── repo_scanner.py       # Repository indexing & chunking
│   ├── ai_parser.py          # Code parsing & embeddings
│   └── file_processor.py     # File upload & text extraction
│
├── assets/                   # Static assets
│   ├── auth.json            # Authentication schemas
│   └── scan.json            # Scan configuration
│
├── data/                     # Data directory
│   └── repos/               # Indexed repositories storage
│
├── .trash/                   # Cleanup folder (unnecessary files)
│   ├── vault_v4.db          # Old database backups
│   ├── vault_v5.db*         # Old database files
│   ├── launcher.py          # Deprecated launcher
│   ├── index.html           # Unused HTML file
│   └── .devcontainer/       # Container config (if not needed)
│
├── .streamlit/              # Streamlit configuration
└── .git/                    # Version control

```

## 🗂️ File Organization Summary

### Removed & Archived (in .trash/)
- ❌ `vault_v4.db`, `vault_v5.db*` - Old database snapshots
- ❌ `launcher.py` - Deprecated launcher (use `streamlit run` instead)
- ❌ `index.html` - Unused HTML file
- ❌ `__pycache__/` - Compiled Python caches
- ❌ `backend/requirements.txt` - Redundant (use main requirements.txt)
- ❌ `.devcontainer/` - Container setup (if not required)

### Core Application Files

#### Main Entry Point
- **`streamlit_app.py`** (1813 lines)
  - Page configuration & theming
  - Authentication (login/signup)
  - Menu navigation system
  - Six main features:
    - Ingest (repository scanning)
    - Explorer (vault browsing)
    - Architect (AI chat + retrieval)
    - Analytics (usage metrics)
    - Admin Dashboard (system control)

#### Backend Modules
- **`backend/db_connector.py`** - SQLAlchemy ORM
  - User, Hub, ChatMessage, SearchHistory models
  - Database initialization & migrations
  
- **`backend/repo_scanner.py`** - Repository Processing
  - Git repository cloning & analysis
  - AST-based code chunking
  - Metadata extraction
  
- **`backend/ai_parser.py`** - AI/ML Operations
  - Semantic embedding generation
  - Code snippet analysis
  - Vector similarity search
  
- **`backend/file_processor.py`** - File Operations
  - PDF/DOCX extraction
  - Text chunking & preprocessing

#### Configuration Files
- **`.env`** - Local environment variables (git-ignored)
  - `GROQ_API_KEY` - API key for Llama 3.3 model
  
- **`.env.example`** - Template for setup
  
- **`requirements.txt`** - Python dependencies

## 🏗️ Code Structure (streamlit_app.py)

### Section 1: Imports & Backend Loading (Lines 1-85)
```python
- Standard/Third-party imports
- Environment setup (load_dotenv)
- Backend module loader (cached for performance)
```

### Section 2: Session State & Utilities (Lines 86-150)
```python
- Session state initialization
- Icon/Card rendering utilities
```

### Section 3: Styling & Theme System (Lines 150-400)
```python
- Global CSS (gradients, animations, borders)
- Theme variables (Dark/Light/System modes)
- Theme application function
```

### Section 4: Authentication (Lines 400-600)
```python
- Password hashing (bcrypt)
- Login/Signup forms
- Session token management
```

### Section 5: Core Operations (Lines 600-1000)
```python
- Database initialization
- Repository scanning (background threads)
- File processing
- Hybrid search (keyword + vector)
```

### Section 6: UI Features (Lines 1000-1750)
```python
- Ingest (repo/file upload)
- Explorer (browse indexed code)
- Architect (AI chat with RAG)
- Analytics (metrics display)
- Admin Dashboard (system control)
```

### Section 7: Sidebar & Navigation (Lines 1750-1813)
```python
- Navigation menu
- User info display
- System controls
- Theme toggle
- Status indicators
```

## 🔒 Security Improvements

✅ **API Key Management**
- Hardcoded GROQ key removed
- Now loaded from `.env` via `os.getenv('GROQ_API_KEY')`
- Error handling for missing keys

✅ **Password Security**
- bcrypt hashing with salt
- Secure password verification

✅ **Database Protection**
- SQLite with proper schema migrations
- User isolation via `user_id` filtering

✅ **Session Management**
- Cookie-based authentication
- 7-day token expiration
- "Remember me" option

## 🚀 How to Run

1. **Setup Environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your GROQ_API_KEY
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Application**
   ```bash
   streamlit run streamlit_app.py
   ```

4. **Access Application**
   ```
   http://localhost:8501
   ```

## 📊 Database Models

- **User** - Authentication & profile
- **Hub** - Indexed code repositories
- **ChatMessage** - Conversation history
- **SearchHistory** - Query logging
- **FileMetadata** - Uploaded files info
- **Satellite** - Code metrics & complexity
- **KeyPool** - Global API credentials

## 🔍 Key Features

- 🧠 **AI Architect Chat** - Ask questions about your codebase with AI reasoning
- 🔍 **Neural Search** - Vector-based semantic code search (integrated in chat)
- 📦 **Vault Explorer** - Browse indexed repositories
- 📊 **Analytics** - Usage metrics & insights
- 🔐 **Admin Dashboard** - Global system control
- 🎨 **Theme System** - Dark/Light/System mode support
- 📱 **Responsive UI** - Works on all screen sizes

## 💡 Code Quality Improvements Made

✅ Better import organization
✅ Clearer section headers
✅ Improved session state management
✅ Utility functions with docstrings
✅ Removed redundant code
✅ Environment-based configuration
✅ Archived unnecessary files

## 📝 Future Improvements

- [ ] Add type hints throughout
- [ ] Extract utility functions to separate modules
- [ ] Add comprehensive logging
- [ ] Implement rate limiting
- [ ] Add unit tests
- [ ] Create API documentation

---

**Last Updated:** May 4, 2026
**Version:** 2.5.9
