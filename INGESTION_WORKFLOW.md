# 🛰️ AI CODE VAULT - INGESTION WORKFLOW ANALYSIS

## Overview
The ingestion process in AI Code Vault 2.0 handles two input types: **GitHub repositories** and **local file uploads**. Both flow through a unified indexing pipeline that converts code into vector-indexed "Hubs".

---

## 📊 INGESTION FLOW ARCHITECTURE

```
User Input (Git URL / File Upload)
    ↓
[REPOSITORY SCANNER] - get_repo_chunks()
    • Clone GitHub repo OR read local files
    • Extract code/documentation
    • Chunk large files (1500 char chunks with 100 char overlap)
    ↓
[CODE PARSER] - parse_code_chunk()
    • Uses Groq LLaMA API (or fallback local parser)
    • Identifies: functions, classes, components, modules
    • Extracts relationships and metadata
    • Generates vector embeddings (1536-dim)
    ↓
[DATABASE INDEXING] - Hub Model
    • Stores parsed chunks as "Hubs"
    • Saves embeddings for semantic search
    • Links satellite metadata (metrics, complexity)
    • Associates with user_id for multi-tenancy
    ↓
[UI PROGRESS DISPLAY]
    • Real-time progress bar (0-100%)
    • Status updates every 2 seconds
    • Shows ETa and chunk count
```

---

## 🔄 STEP-BY-STEP INGESTION PROCESS

### **Phase 1: Repository Scanning (get_repo_chunks)**
Located in: `backend/repo_scanner.py`

**What happens:**
```python
def get_repo_chunks(repo_url: str) -> List[Dict]:
    # Input: GitHub URL or local path
    
    1. Check if URL is GitHub format
       → Yes: Clone with --depth=1 (shallow clone for speed)
       → No: Treat as local directory path
    
    2. Traverse directory recursively
       • Ignore: node_modules, .git, __pycache__, .env
       • Include: .py, .js, .ts, .jsx, .tsx, .html, .css, .md, .json, .sql
    
    3. Extract code files and read content
       • For code files: Extract raw source
       • For docs: Extract markdown/text
       • For data: Treat as searchable content
    
    4. Create "chunks" - dict with:
       {
           "name": "filename_or_function_name",
           "code": "actual code content",
           "file_path": "path/in/repo",
           "type": "function|class|module|document"
       }
    
    5. Return: List of all chunks found
```

**Output:** List of dictionaries, each representing a code unit

---

### **Phase 2: Code Parsing & Embedding (parse_code_chunk)**
Located in: `backend/ai_parser.py`

**What happens:**
```python
def parse_code_chunk(chunk: Dict) -> Dict:
    # Input: Single code chunk from scanner
    
    1. Call Groq LLaMA API with SYSTEM_PROMPT
       • Model: "llama-3.3-70b-versatile" (heavy analysis)
       • Analyzes the code semantically
       • Identifies function name, calls, parameters, complexity
    
    2. API Response Parsing (if Groq available)
       Expected JSON output:
       {
           "hub": {
               "hash_key": "function_name",
               "type": "function|class|component|module",
               "code_snippet": "...",
               "embedding": [0.123, 0.456, ...] (1536 floats)
           },
           "links": [...],  // References to other code
           "satellite": {...}  // Metadata
       }
    
    3. Fallback Parsing (if Groq fails)
       • Use local SHA256-based embedding generator
       • Deterministic: same code always produces same vector
       • Allows app to work without API
    
    4. Generate Vector Embedding
       • Method: SHA256 hash → numpy seed → random vector
       • Dimension: 1536 (OpenAI compatible)
       • Used for semantic search later
    
    5. Return: Parsed hub data with embedding
```

**Output:** Structured hub object ready for database

---

### **Phase 3: Database Indexing (Hub Storage)**
Located in: `backend/db_connector.py`

**What happens:**
```python
# For each successfully parsed chunk:

new_hub = Hub(
    hash_key="function_name",           # Unique identifier
    code_snippet="actual code here",    # Source code
    embedding_vector=[...],             # 1536-dim vector
    user_id=123,                        # Multi-tenant isolation
    repo_url="https://github.com/...",  # Source tracking
    type="function|class|module"        # Entity type
)
scan_session.merge(new_hub)  # Insert or update

# Progress tracking in User model:
user.scan_progress = 45              # Percentage (0-100)
user.scan_status = "Indexing: 45/100 chunks — ETA 2m 30s"
scan_session.commit()                # Push to DB
```

**Database Schema:**
- **Hub Table**: Core indexed code units
- **Satellite Table**: Metadata (LOC, complexity, parameters)
- **FileMetadata Table**: Uploaded file tracking
- **SearchHistory Table**: Query tracking for analytics

---

### **Phase 4: Real-Time UI Progress Display**

**Frontend (streamlit_app.py):**
```python
# Every 1.5 seconds:
1. Query database for current user's scan status
2. Read: User.scan_progress, User.scan_status
3. Display:
   - Progress bar (animated gradient 0-100%)
   - Status text: "Indexing: 45/100 chunks — ETA 2m 30s"
   - Pulse animation to indicate activity
4. Rerun Streamlit to refresh display

# User can click "Stop Ingestion" to:
- Set abort_event flag
- Clear scan_progress and scan_status
- Halt background thread gracefully
```

**Visual Output:**
```
🛰️ NEURAL SCAN IN PROGRESS
▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░ 45%

Stage: Indexing: 45/100 chunks — ETA 2m 30s
⏳ Processing Neural Chunks...
```

---

## 🚀 BACKGROUND WORKER PROCESS

**Function:** `background_scan_task(repo_url, user_id, abort_event)`

```python
# Runs in separate thread to prevent UI blocking

1. Get repo chunks from scanner
2. For each chunk (with progress tracking):
   a. Check if user clicked "Stop" (abort_event)
   b. Parse chunk with AI parser
   c. Create Hub object in database
   d. Every 2 seconds: Update User.scan_progress in DB
   
3. When complete:
   - Update User.scan_status = "Complete — 523 code hubs indexed"
   - UI detects completion and shows success toast
   
4. On error:
   - Update User.scan_status = "Critical Failure: {error message}"
   - Stack trace logged to /tmp/vault_v6_debug.log
```

---

## 📁 FILE UPLOAD INGESTION

**Function:** `process_file_content(uploaded_file, user_id)`

```python
# Alternative ingestion path for individual files

1. Accept file types: py, js, ts, jsx, tsx, html, css, md, json, sql, pdf, docx, txt, csv

2. Extract text from file:
   - .txt/.code: Raw text read
   - .pdf: PyPDF2 extraction
   - .docx: python-docx extraction
   - Others: Plain text fallback

3. Chunk large files:
   - If > 2000 chars: Split into 1500-char chunks (100 overlap)
   - If < 2000 chars: Process as single unit

4. For each chunk:
   - Parse with AI parser (same as repo scanning)
   - Create Hub in database
   - Track progress

5. Store FileMetadata:
   - Filename, extension, size, upload timestamp
   - Used by Explorer tab to list all uploaded files
```

---

## 🔍 GROQ API INTEGRATION

**Configuration:**
```python
# In ai_parser.py:
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # From .env file

# Models used:
PRIMARY_MODEL = "llama-3.3-70b-versatile"    # Heavy code analysis
FAST_MODEL = "llama-3.1-8b-instant"         # Light operations

# System prompt tells LLaMA to:
# - Identify main entity (function, class, etc.)
# - List outgoing references/calls
# - Extract metrics (LOC, complexity, parameters)
# - Return structured JSON
```

**Graceful Fallback:**
```python
if GROQ_API_KEY is missing or invalid:
    → Use local SHA256-based embedding
    → App continues to work offline
    → Vector quality reduced but functional
```

---

## 💾 DATA PERSISTENCE

**What gets saved during ingestion:**

| Table | What | Purpose |
|-------|------|---------|
| **Hub** | Code chunks with embeddings | Semantic search index |
| **Satellite** | Metrics (LOC, complexity) | Analytics & insights |
| **FileMetadata** | File info & upload history | File tracking |
| **SearchHistory** | User queries | Analytics |
| **ChatMessage** | Architect AI conversations | Context memory |

---

## ⚡ PERFORMANCE OPTIMIZATIONS

1. **Shallow Git Cloning:** `--depth=1` (only latest commit)
2. **Throttled UI Updates:** Progress bar updates every 2 seconds (not every chunk)
3. **Database Batching:** Multiple chunks committed in single transaction
4. **Chunking Strategy:** 1500-char chunks with 100-char overlap = semantic continuity
5. **Background Threading:** Ingestion doesn't block UI thread
6. **User-Cancelable:** Stop button with abort_event flag

---

## 🛠️ DEBUGGING & TELEMETRY

**Access via UI:**
- Menu → Ingest → Expander: "🛠️ System Telemetry Logs (V6.1)"
- Shows last 50 lines of `/tmp/vault_v6_debug.log`
- Each debug message prefixed with `[SCANNER_DEBUG]` or `[WORKER_*]`

**Example log output:**
```
[SCANNER_DEBUG] Cloning GitHub repo: https://github.com/fastapi/fastapi
[WORKER] Started background_scan_task for https://... (User: 42)
[WORKER] Starting indexing phase for 523 chunks.
[WORKER] Task Complete. Indexed 519 chunks.
```

---

## 🔐 SECURITY & MULTI-TENANCY

- **User Isolation:** All queries filter by `user_id`
- **Session Tokens:** Persistent login via cookies
- **API Key Management:** Groq key stored in `.env` (git-ignored)
- **Database Encryption:** SQLite with connection pooling

---

## 📈 METRICS TRACKED DURING INGESTION

```python
user.scan_progress: int           # 0-100 percentage
user.scan_status: str             # "Indexing: N/total — ETA Xm Ys"
hub.embedding_vector: float[]     # 1536-dim vector for similarity
satellite.metrics: dict           # {"lines_of_code": 42, "complexity": "medium"}
file_metadata.upload_date: datetime  # When file was added
```

---

## 🎯 KEY TAKEAWAYS

✅ **What the ingestion system does:**
1. Accepts GitHub URLs or file uploads
2. Extracts code and documentation
3. Parses with AI (Groq LLaMA) or local fallback
4. Generates semantic embeddings
5. Indexes in database for search/retrieval
6. Displays real-time progress to user

✅ **Why it's designed this way:**
- **Modular:** Scanner, Parser, Indexer are separate
- **Resilient:** Works with or without API
- **Real-time:** Progress updates every 2s
- **Fast:** Shallow clones, throttled updates
- **Scalable:** Chunking strategy handles large repos
- **Secure:** Per-user data isolation

---

## 🚀 Next Steps After Ingestion

After indexing completes:
- **Explorer Tab:** View all indexed hubs and files
- **Vault Explorer:** Search and analyze code units
- **Architect Tab:** Use AI to query the indexed codebase
- **Analytics Tab:** View ingestion statistics

