# Backend Source Code Reference — AI Code Vault 2.0

This document contains a comprehensive, line-by-line (or logical block-by-block for large sections) explanation of all files inside the `backend/` directory of **AI Code Vault 2.0 (v2.5.9)**.

---

## 1. `backend/__init__.py`

This is the initialization file of the `backend` Python package. It contains 8 lines.

### Code & Line-by-Line Breakdown:
```python
# Backend Package
"""
AI CODE VAULT 2.0 - Backend Modules
Handles database, repository scanning, AI parsing, and file processing.
"""

__version__ = "2.5.9"
```

- **Lines 1–5**: Documentation strings explaining the namespace and high-level responsibilities of the backend modules (database ORM, repository scanning, AST/LLM parsing, and document upload processor).
- **Line 7**: Defines the global package version metadata string (`__version__ = "2.5.9"`), which is referenced by the UI during health checks and diagnostics.

---

## 2. `backend/embeddings.py`

This file handles the generation of vector representations for both code snippets and document chunks. It tries to run locally for privacy and cost reasons, falling back to a deterministic simulation if PyTorch/Transformers are missing.

### Code & Line-by-Line Breakdown:

#### Imports & Global Variables (Lines 1–27):
- **Lines 1–9**: Package docstring describing pluggable provider capabilities.
- **Line 10**: Imports `List` from `typing` for strict type hinting of embedding float arrays.
- **Line 11**: Imports `os` to fetch configuration values from system environments.
- **Lines 13–14**: Declares global variables `_model` (stores the local sentence-transformer pipeline) and `_use_local` (flag indicating if dependencies exist).
- **Lines 16–20**: A `try-except` block attempting to import `SentenceTransformer`. If successful, `_use_local` is set to `True`; otherwise, it degrades gracefully to `False`.
- **Line 23**: Defines `_DEFAULT_MODEL` by reading the `LOCAL_EMBEDDING_MODEL` environment variable, defaulting to `'all-MiniLM-L6-v2'` (a fast 384-dimensional model).
- **Lines 25–26**: Imports standard libraries `hashlib` (for hashing fallback seeds) and `numpy` (for pseudo-random vector generation).

#### Initialization Pipeline (Lines 29–36):
```python
def _init_local_model():
    global _model
    if _model is None and _use_local:
        try:
            _model = SentenceTransformer(_DEFAULT_MODEL)
        except Exception:
            _model = None
```
- **Lines 29–36**: `_init_local_model()` implements a lazy load pattern. It instantiates the `SentenceTransformer` class only on the first vector generation request, preventing startup lag. If it fails (e.g. disk quota or download failures), it resets `_model` to `None`.

#### Single-Text Vectorizer (Lines 38–57):
```python
def get_embedding(text: str) -> List[float]:
    """Return an embedding for a single text."""
    if not text:
        return [0.0] * 1536

    if _use_local:
        _init_local_model()
        if _model is not None:
            try:
                vec = _model.encode(text)
                return [float(x) for x in vec.tolist()]
            except Exception:
                pass

    # Deterministic SHA256 -> seeded random fallback (1536 dims)
    hash_obj = hashlib.sha256(text.encode('utf-8'))
    seed = int(hash_obj.hexdigest(), 16) % (2**32)
    rng = np.random.RandomState(seed)
    return rng.rand(1536).tolist()
```
- **Lines 38–41**: Checks if input text is empty or blank. If so, returns a zero-vector of 1536 dimensions as a safe fallback.
- **Lines 43–51**: If local setup is enabled, initializes the model and runs `_model.encode(text)`. The output vector is converted to standard Python float values and returned.
- **Lines 53–57**: **The Fallback Engine**. If the local library is absent or crashes, it hashes the input text using SHA256. It takes the digest, converts it to an integer, bounds it to a valid 32-bit unsigned range (`2**32`), seeds a `numpy.random.RandomState` instance, and returns a deterministic array of 1536 random values. Because it uses the text as a seed, the exact same text will *always* generate the exact same vector, preserving vector search logic.

#### Batch Vectorizer (Lines 60–72):
- **Lines 60–69**: Evaluates if the local transformer model is active. If so, encodes the list of texts in a single batch pass, which is significantly faster than single execution loops on GPUs or CPUs.
- **Line 71**: If local processing fails, list-comprehends over the input array using `get_embedding(t)` to generate individual simulated vectors.

---

## 3. `backend/ai_parser.py`

This module parses raw code snippets into structural metadata, relationships (links), and complexity metrics. It uses local AST checks for Python, and relies on LLM prompts for other files.

### Code & Line-by-Line Breakdown:

#### Declarations & Setup (Lines 1–30):
- **Lines 1–8**: Imports parsing libraries (`ast`, `json`), vector utility (`get_embedding` as `generate_embedding`), LLM handler (`Groq`), and type hints.
- **Line 10**: Invokes `load_dotenv()` to read configurations.
- **Lines 13–15**: Fetches `GROQ_API_KEY`, `GROQ_MODEL`, and `GROQ_FAST_MODEL` env parameters.
- **Lines 17–26**: Instantiates the `Groq` client. If initialization fails (e.g. missing API keys), it prints a warning to logs and sets the `client` handler to `None` for fallback execution.

#### Local AST Complexity Estimator (Lines 32–42):
```python
def _estimate_complexity_from_ast(node: ast.AST) -> str:
    """Simple heuristic to estimate complexity from AST nodes."""
    counter = 0
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.IfExp, ast.BoolOp)):
            counter += 1
    if counter < 5:
        return 'Low'
    if counter < 15:
        return 'Medium'
    return 'High'
```
- **Lines 32–37**: Walks the Abstract Syntax Tree of Python source code, counting conditional branches, loops, exception catch statements, and boolean operations.
- **Lines 38–42**: Classifies the code's complexity: `< 5` yields 'Low', `< 15` yields 'Medium', and higher counts yield 'High'.

#### Deterministic Python Parser (Lines 45–115):
- **Lines 45–67**: Attempts to generate an AST using `ast.parse()`. If parsing fails (e.g., due to syntax errors), it skips AST checks and returns a generic metadata payload with a 'Medium' complexity rating.
- **Lines 69–70**: Filters root-level AST nodes to identify all function and class definitions.
- **Lines 72–86**: Classifies the parsed chunk:
  - If it contains exactly one function and no classes, the hub is categorized as a `'function'` with its name as the `hash_key`, and we extract its parameter names.
  - If it contains exactly one class and no root-level functions, the hub is categorized as a `'class'`.
  - Otherwise, it is classified as a generic `'module'` using the file's basename as its identity.
- **Lines 88–95**: Scrapes function calls (`ast.Call` nodes) to map execution relationships (e.g., `calls` relationship links).
- **Lines 97–114**: Runs the complexity estimator and builds the final Data Vault 2.0 parser output dictionary.

#### Parsing Fallbacks (Lines 118–139):
- **Lines 118–139**: `fallback_parse` creates a baseline payload for raw code chunk objects. It computes local vector embeddings, counts lines of code by splitting on `\n`, and sets default complexity to `'Medium'`.

#### Main Parser Entrypoint (Lines 142–198):
- **Lines 142–151**: `parse_code_chunk` receives raw code. If the code string is empty, it returns the generic fallback payload.
- **Lines 153–154**: Extracts file extension to determine the parsing logic.
- **Lines 156–162**: If the extension points to a Python file, it executes the local AST-based parser.
- **Lines 164–166**: If the file is not Python and the Groq LLM client is missing, it falls back to basic metadata parsing.
- **Lines 168–198**: Uses the Groq client to parse non-Python formats. It structures a prompt requesting JSON output (keys: `hub`, `links`, `satellite`), sends the code chunk, cleans code-block syntax indicators from the response text, decodes the JSON, generates a vector embedding, and attaches it back to the parsed payload. If an LLM call fails, it falls back to `fallback_parse`.

---

## 4. `backend/repo_scanner.py`

This module clones Git repositories (or downloads ZIP archives if CLI tools are missing), walks directory trees, and chunks files for indexers.

### Code & Line-by-Line Breakdown:

#### Windows Read-Only Cleanup (Lines 16–25):
```python
def _win_on_rm_error(func, path, exc_info):
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception:
        pass
```
- **Lines 16–25**: A helper for deleting Git directories on Windows. Git keeps certain files read-only, which causes standard `shutil.rmtree` calls to fail. This handler catches errors, updates permissions using `os.chmod` to write-only/owner executable (`0o700`), and retries deletions.

#### Git Accessibility Validator (Lines 28–42):
- **Lines 28–42**: Checks if a resource is accessible. If it is a remote repository URL, it executes `git ls-remote <url>` with a timeout. If it is a local path, it checks `os.path.exists`.

#### Debug Log Management (Lines 44–56):
- **Lines 44–56**: Appends structured debug trace text to a local log file (`vault_v6_debug.log` in temporary folders) and prints it to stdout.

#### GitHub Downloader & API Fallback (Lines 62–126):
- **Lines 62–88**: Generates a temporary directory. Attempts to clone the repository with a shallow clone (`--depth 1`) using `git clone`.
- **Lines 89–120**: **API Fallback**. If the command-line git tool is missing, it extracts the repo owner/slug, requests a ZIP archive via the GitHub API (`/repos/{owner}/{repo}/zipball`), writes the ZIP archive locally, extracts it to the temporary folder, and returns the path. If both methods fail, it cleans up and raises an exception.

#### Directory Walk & Chunking Engine (Lines 128–233):
- **Lines 128–154**: Sets up supported files lists and resolves GitHub urls vs. local directories.
- **Lines 159–161**: Customizes directory traversals: skips `.git`, `node_modules`, `venv`, `__pycache__`, `dist`, and `build` folders to optimize indexing.
- **Lines 169–182**: Notebook Parser. If it detects a Jupyter notebook (`.ipynb`), it parses the JSON structure, extracts code-cell contents, and joins them into a unified script, ignoring markdown explanations.
- **Lines 184–201**: Line-aware text splitter. If a file's content exceeds the chunk size, it splits text by line and joins lines together until they reach `max_chunk_size` characters, preserving structural line breaks.
- **Lines 203–214**: Constructs a metadata record for each chunk.
- **Lines 224–233**: Executes cleanup inside the `finally` block to ensure cloned repositories are deleted from temporary storage.

#### Heuristics (Lines 235–290):
- **Lines 235–250**: Maps file extensions to programming languages.
- **Lines 252–277**: Computes simple metrics for chunk code: count of lines, code statements, functions, classes, and complexity.
- **Lines 279–290**: Simple keyword-based cyclomatic complexity evaluator: counts control words like `if`, `else`, `for`, `while`, etc., to categorize complexity.

---

## 5. `backend/file_processor.py`

This module extracts text from standard document formats (PDF, DOCX, CSV) and writes them to the Data Vault 2.0 database.

### Code & Line-by-Line Breakdown:

#### Document Text Extraction (Lines 10–101):
- **Lines 10–37**: Main dispatcher. Routes file reads to dedicated extractors based on file extension.
- **Lines 39–55**: **CSV Extractor**. Reads CSV files using `pandas`. It joins row columns with a pipe separator (`Column: Value | Column: Value`) and appends an internal marker `__CSV_ROW_BOUNDARY__` to keep individual rows separate.
- **Lines 57–68**: Plain Text Extractor. Reads files using UTF-8 encoding, ignoring encoding errors.
- **Lines 70–85**: **PDF Extractor**. Reads PDFs using `PyPDF2`, extracting text page-by-page.
- **Lines 87–101**: **DOCX Extractor**. Iterates paragraphs in Microsoft Word files using `python-docx` to extract text.

#### Sentence-Aware Text Chunker (Lines 103–139):
```python
def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    chunks = []
    if len(text) <= chunk_size:
        return [text]
    
    # Split by sentences first
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(chunks) > 0:
                current_chunk = chunks[-1][-overlap:] + " " + sentence + " "
            else:
                current_chunk = sentence + " "
    ...
```
- **Lines 103–122**: Splits long text files by sentence using a regular expression that matches punctuation (`.`, `!`, `?`) followed by whitespace.
- **Lines 123–139**: Iterates through sentences, grouping them into chunks of up to `chunk_size` characters. When a chunk is full, it appends the trailing `overlap` characters to the beginning of the next chunk to preserve context across boundaries.

#### File Validation & Metadata Helpers (Lines 141–200):
- **Lines 141–180**: Checks if an uploaded file exists, verifies that its size does not exceed limits (e.g., 50MB), and checks if its extension is supported.
- **Lines 182–200**: Extracts file metadata (filename, size, creation and modification timestamps, extension) using system utility calls.

#### Data Vault Ingestion pipeline (Lines 202–364):
- **Lines 202–233**: Inserts a new file tracking record in the `documents` table with status set to `'processing'`.
- **Lines 236–254**: Parses file contents. For CSVs, it reads columns and updates the metadata record. For other files, it splits text using the sentence-aware chunker.
- **Lines 266–298**: **Hub and Link Registration**. Computes MD5 hash keys for the document and user, checking for existing entries to avoid duplicates. It then links the user to the document in `LinkUserDocument`.
- **Lines 304–336**: **Chunk-by-Chunk Satellite Loader**. Iterates through the text chunks, computing a unique hash diff for each. It writes the chunk text to `SatDocumentContent`, generates a vector representation, and writes it to `SatDocumentEmbedding`.
- **Lines 337–342**: **Progressive Commit**. Commits changes to the database every 10 chunks to prevent memory bloat and timeouts.
- **Lines 343–364**: Updates the final chunk count, sets status to `'complete'`, and commits the transaction. If an error occurs, it rolls back changes and updates status to `'failed'`.

---

## 6. `backend/db_connector.py`

This module defines the database models and operations, implementing a Data Vault 2.0 architecture in SQLite.

### Code & Line-by-Line Breakdown:

#### Imports & Engine Setup (Lines 1–17):
- **Lines 5–12**: Imports SQLAlchemy modules, JSON converters, hashing libraries, and thread-safe pool objects.
- **Lines 15–16**: Sets up the base class for declarative models and configures the default SQLite database path (`vault_v5.db`).

#### Core Application Models (Lines 22–122):
- **Lines 22–35**: **User**: Holds user accounts, password hashes (supports both legacy and current formats), active session tokens, authorization roles (`User`/`Admin`), and scanning status.
- **Lines 37–54**: **Hub**: Stores repository code snippets, complexity metrics, and project mapping scopes. Uses a composite unique constraint to scope keys to specific users.
- **Lines 56–64**: **ChatMessage**: Stores chat messages (user prompt vs. agent response) mapped to user IDs.
- **Lines 66–74**: **SearchHistory**: Stores search logs for user activity dashboards.
- **Lines 76–85**: **FileMetadata**: Stores statistics for file uploads.
- **Lines 87–93**: **Satellite**: Stores code analysis metrics.
- **Lines 95–104**: **KeyPool**: Manages LLM API keys.
- **Lines 107–121**: **ScanJob**: Tracks asynchronous repository ingestion tasks.

#### Data Vault 2.0 Hubs (Lines 127–165):
These tables store unique business keys with tracking details.
- **HubCode**: Tracks unique source code entities.
- **HubRepository**: Tracks crawled repositories.
- **HubUser**: Tracks registered user emails.
- **HubDocument**: Tracks document filenames.

#### Data Vault 2.0 Links (Lines 171–202):
These tables establish relationships between hubs.
- **LinkCodeRepository**: Links code units to their source repositories.
- **LinkUserRepository**: Links users to their crawled repositories.
- **LinkUserDocument**: Links users to their uploaded documents.

#### Data Vault 2.0 Satellites (Lines 208–337):
These tables store descriptive metadata over time (insert-only design).
- **SatCodeContent**: Stores the raw content, language, and path of code snippets.
- **SatCodeMetrics**: Tracks complexity metrics over time.
- **SatCodeEmbedding**: Stores vector embeddings for code snippets.
- **SatDocumentContent**: Stores raw text for document chunks.
- **SatDocumentEmbedding**: Stores vector embeddings for document chunks.
- **SatUserProfile**: Stores user settings and preferences (e.g. theme).

#### Evaluation Checklist Models (Lines 343–389):
- **Document**: Tracks document files.
- **Search**: Logs search terms, scores, and response times.
- **Feedback**: Stores thumbs up/down feedback and comments.

#### Index Definitions (Lines 391–399):
- **Line 395**: Creates a composite index `idx_hubs_user_repo` on `(user_id, repo_url)` to optimize search performance.

#### Hash Generators (Lines 405–425):
```python
def compute_hash_key(*args):
    raw = '||'.join(str(a) for a in args)
    return hashlib.md5(raw.encode('utf-8')).hexdigest()
```
- **Lines 405–412**: `compute_hash_key` concatenates business keys using the separator `||` and generates an MD5 hash, serving as the record's primary key.
- **Lines 415–425**: `compute_hash_diff` converts attributes into a sorted JSON string and hashes it. If the hash matches an existing record, the system skips writing it, preventing duplicate entries.

#### Tenant Isolation Helper (Lines 428–437):
- **Lines 428–437**: `get_user_scoped_query` scopes database queries to the current user's ID to enforce row-level security.

#### Insert-Only Loader (Lines 444–524):
```python
def load_data_vault(session, hub_model, satellite_model, hub_data, sat_data,
                    hub_hash_key, record_source='vault_app',
                    hub_fk_column='hub_code_hash'):
    ...
```
- **Lines 479–491**: Checks if a hub record already exists; if not, inserts it.
- **Lines 493–512**: Computes a new hash diff for the satellite data and checks it against the active satellite record (where `load_end_date` is null). If the data hasn't changed, the update is skipped. If it has, the active record is closed by setting its `load_end_date` to the current timestamp.
- **Lines 514–524**: Inserts a new active version of the satellite record.

#### Temporal Point-in-Time Query (Lines 531–564):
- **Lines 531–564**: Returns the active satellite record for a given timestamp by checking if `load_date <= as_of_datetime` and `load_end_date > as_of_datetime` (or null).

#### Hybrid Search (Lines 571–862):
- **Lines 586–590**: Tokenizes search queries into lowercase terms.
- **Lines 591–606**: Resolves the user's files and documents.
- **Lines 616–674**: Evaluates whether the user's query references specific filenames, directories, or paths, using matching to narrow search results.
- **Lines 677–776**: Runs keyword filtering. Builds a query using SQL `LIKE` conditions for the search terms. If it returns no matches, the system retrieves all records for the user to allow semantic fallback.
- **Lines 778–859**: Calculates similarity scores. Computes the cosine similarity between the query embedding and candidate document embeddings. It then calculates the hybrid score using a weighted average: `0.7 * semantic + 0.3 * keyword`.
- **Lines 860–862**: Sorts results by hybrid score descending and returns the top `top_k` matches.

#### Analytical Views (Lines 869–944):
- **Lines 869–944**: `create_views` defines 4 analytical SQL views on database initialization:
  - `user_activity_summary`: Aggregates usage metrics per user.
  - `document_search_summary`: Maps document statistics to search events.
  - `complex_code_units`: Identifies code snippets with medium to high complexity.
  - `search_analytics`: Computes response times and activity timestamps.

#### Initialization & Auto-Migrations (Lines 950–1080):
- **Lines 950–960**: Configures the SQLAlchemy database engine, enabling thread-safe settings for SQLite.
- **Lines 962–1008**: **Database Initialization**. Recreates database tables if constraint changes are detected, creates analytical SQL views, and applies migrations.
- **Lines 1010–1054**: **Schema Migration**. Checks existing database schemas and adds missing columns (e.g. `session_token` in `users`, `column_names` in `documents`, etc.) to maintain backward compatibility.
- **Lines 1055–1080**: Checks if database files exist and returns active table structures for diagnostic panels.

---

## 7. `backend/agent.py`

This module implements the agent routing and orchestration logic, routing user requests to specialist agents.

### Code & Logical Block Breakdown:

Because `backend/agent.py` is 1271 lines long, we break down the file by its logical sections and core functional pipelines.

#### Imports, Setup & Key Resolution (Lines 1–110):
- **Imports**: Imports core libraries (`os`, `re`, `shutil`, `zipfile`, `difflib`, `uuid`, `threading`), database models, and the parsing pipeline.
- **`AgentResult`**: A structured data class representing agent outputs:
  ```python
  class AgentResult:
      def __init__(self, answer, steps=None, tools_used=None, active_agent=None, artifacts=None):
          self.answer = answer
          self.steps = steps or []
          self.tools_used = tools_used or []
          self.active_agent = active_agent
          self.artifacts = artifacts or {}
  ```
- **`_resolve_api_key`**: Resolves LLM API keys in order of priority: checks session state configurations, then checks environment variables (`GROQ_API_KEY`), and finally falls back to active entries in the database key pool.

#### LLM Executor (Lines 112–158):
- **`_call_llm`**: Executes calls to the Groq API. It resolves the API key, selects the model (defaulting to Llama 3.3 70B), builds the payload, and sends the request. If the API key is missing or the call fails, the system throws an error.

#### Supervisor Routing Engine (Lines 160–250):
- **`SupervisorAgent`**: Directs user queries to the appropriate agent. It first uses regular expression checks to scan queries for keyword patterns:
  - If matches keywords like `edit`, `patch`, or `update`, routes to the **Patch Generator**.
  - If matches keywords like `test`, `unittest`, or `assert`, routes to the **Test Strategist**.
  - If matches keywords like `review`, `bug`, or `vulnerability`, routes to the **Code Reviewer**.
  - If matches keywords like `quiz`, `question`, or `trivia`, routes to the **Quiz Agent**.
  - If matches keywords like `extract` or `table`, routes to the **Extract Agent**.
  - If matches keywords like `explain` or `summarize`, routes to the **Documentation Agent**.
  - If matches keywords like `architecture` or `design`, routes to the **Analysis Agent**.
  - If matches keywords like `zip` or `export`, routes to the **Zip Export Agent**.
- **LLM Fallback Router**: If keyword patterns don't match, the Supervisor sends the query to the fast LLM (`llama-3.1-8b-instant`) with a list of available agents, using the LLM's classification to route the request.

#### Specialist Agent Implementations (Lines 252–900):

##### 1. RAG Q&A Agent (`RAGAnswerAgent`)
Runs vector-based hybrid searches on the database using the query. If matches are found, it injects the code snippets and text chunks into the prompt context and instructs the LLM to answer using only the provided context.

##### 2. Patch Generator (`PatchDiffGenerator`)
Handles code edits. It runs a search to retrieve the relevant file, presents the code, creates an update plan, and generates unified diffs using the standard library `difflib.unified_diff`. It outputs a downloadable patch file. If the LLM is rate-limited, it falls back to a search-and-replace editor to modify the file.

##### 3. Code Reviewer (`CodeReviewerAgent`)
Analyzes code snippets for code quality, security vulnerabilities (such as injection risks or hardcoded credentials), and performance bottlenecks.

##### 4. Test Strategist (`TestStrategistAgent`)
Generates testing plans. It reviews source code to draft test suites (such as unit, integration, and mock tests) matching the repository's programming language.

##### 5. Documentation Agent (`DocumentationAgent`)
Summarizes code blocks, writes docstrings, and drafts onboarding guides.

##### 6. Zip Export Agent (`ZipExportAgent`)
Packs indexed code files or downloads remote repositories as ZIP archives for users to download.

##### 7. Quiz Agent (`QuizAgent`)
Generates 5-question multiple-choice quizzes from indexed code snippets to test users' understanding.

##### 8. Extract Agent (`ExtractAgent`)
Parses unstructured log or document data into markdown tables.

##### 9. Analysis Agent (`AnalysisAgent`)
Evaluates systems at the architectural level, mapping design patterns and codebase flows.

##### 10. General Agent (`GeneralChatAgent`)
Handles general inquiries that do not require repository search contexts.

#### Unified Execution Entrypoint (Lines 902–980):
- **`run_agent`**: The main function called by `streamlit_app.py`. It initializes the DB connection, creates a history log, calls the `SupervisorAgent` to route the query, runs the selected specialist, logs the transaction, and returns the structured `AgentResult` object.

#### Ingestion Pipeline Engine (Lines 982–1271):
- **`run_ingest_agent`**: Manages the ingestion pipeline.
  - Updates the user's scan progress to `10%` and clones the repository (or downloads the ZIP).
  - Updates progress to `30%`, walks the directory tree, and chunks files.
  - Updates progress to `50%`, then loops through the chunks, using the AST parser for Python files and the LLM parser for other files to extract metadata.
  - Generates embeddings, writes the parsed data to the Data Vault 2.0 tables, and commits changes.
  - Updates progress to `100%`, sets status to `'Idle'`, and cleans up temporary files.
  - If a step fails, the system rolls back database transactions and records the error details.
