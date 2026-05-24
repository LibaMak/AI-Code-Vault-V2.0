# Architecture & Code Structure — AI Code Vault 2.0

This document outlines the architecture, file organization, database schema, and design patterns of **AI Code Vault 2.0 (v2.5.9)**.

---

## 1. Architecture Overview

AI Code Vault 2.0 is designed as a **Multi-Agent Retrieval-Augmented Generation (RAG) system** utilizing a **Data Vault 2.0** database methodology. It combines local semantic processing with LLM-orchestrated coding assistants to index, analyze, and modify codebases.

```
┌─────────────────────────────────┐
│       streamlit_app.py          │  Frontend + Orchestration (138KB)
│         (Streamlit UI)          │
└───────────┬─────────────────────┘
            │ calls run_agent() / run_ingest_agent()
            ▼
┌─────────────────────────────────┐
│         agent.py                │  Supervisor → 10 Specialist Agents
│   SupervisorAgent (router)      │
│   ├─ RAGAnswerAgent             │  Retrieval-augmented Q&A
│   ├─ PatchDiffGenerator         │  Code editing with unified diffs
│   ├─ CodeReviewerAgent          │  Security & quality reviews
│   ├─ TestStrategistAgent        │  Test plan generation
│   ├─ DocumentationAgent         │  Summaries & documentation
│   ├─ ZipExportAgent             │  Repository export
│   ├─ QuizAgent                  │  Knowledge quizzes
│   ├─ ExtractAgent               │  Data extraction
│   ├─ AnalysisAgent              │  Architectural analysis
│   └─ GeneralChatAgent           │  General conversation
└───────┬───────┬─────────────────┘
        │       │
        ▼       ▼
┌──────────┐ ┌──────────────────────┐
│ Groq API │ │   db_connector.py    │
│  (LLM)   │ │ SQLAlchemy ORM       │
└──────────┘ │ Data Vault 2.0       │
             │ Hybrid Search        │
             └──────┬───────────────┘
                    ▼
             ┌──────────────┐
             │  SQLite DB   │
             │ vault_v5.db  │
             └──────────────┘

Ingestion Pipeline:
  repo_scanner.py → ai_parser.py → embeddings.py → db_connector.py
  file_processor.py → embeddings.py → db_connector.py
```

---

## 2. File-by-File Documentation

### `streamlit_app.py`
The main entry point for the user interface. It manages front-end views, styling, routing, and user session states.
- **View Navigation**: Handles routing for 9 distinct views (Auth, Ingest, Smart Search, Explorer, Architect, Analytics, Profile, Admin Dashboard, Admin User Management, Admin Activity Logs) scoped based on user roles (`Admin` or `User`).
- **Session State & Auth**: Implements bcrypt verification, cookie-based session recovery, rate-limited login attempts (5 attempts, 15-min lockout), and theme preference persistence.
- **Custom CSS Design**: Contains over 700 lines of custom CSS defining a premium glassmorphic UI, radial glow animations, custom fonts (`Outfit` and `Inter`), and floating background orbs.
- **Visual Indicators**: Implements the *Neural Stream Terminal* for ingestion logging, *Live Neural Heartbeat* for scan progress, and a *Neural Status Indicator* for active database connections.

### `backend/__init__.py`
Package initialization file. Sets package version metadata to `2.5.9`.

### `backend/agent.py`
The multi-agent orchestration layer. Coordinates interactions between the user and specialist agents.
- **Supervisor routing**: Parses incoming messages using heuristic keyword detection and LLM fallback to route queries to the correct specialist.
- **Specialist Agents**: Details 10 agents (RAG, Patch, Reviewer, Test Strategist, Documentation, Zip Export, Quiz, Extract, Analysis, and General Q&A) equipped with specific instructions.
- **Unified Diff Generation**: Implements `_build_unified_diff` to calculate modifications and output downloadable unified diffs.
- **Heuristic Editor**: Implements deterministic fallbacks when rate-limited by LLM endpoints.

### `backend/ai_parser.py`
Handles chunk-level abstract syntax tree (AST) and LLM-assisted metadata parsing.
- **Python AST Parser**: Zero-cost parser using the Python `ast` module to extract classes, functions, calls, complexity estimates, and line lengths.
- **Polyglot Parser**: Fallback parser utilizing the Groq API to extract structural details from non-Python code as structured JSON.
- **Complexity Estimation**: Evaluates cyclomatic complexity categories (Low, Medium, High).

### `backend/db_connector.py`
The data architecture layer implementing the **Data Vault 2.0** framework. Contains 22 database models and 4 pre-compiled SQL views.
- **Data Vault Loads**: Implements insert-only load patterns (`load_data_vault`) with MD5-based Hash Keys and Hash Diffs for change data tracking.
- **Point-in-Time Queries**: Evaluates the historical state of code and documents using temporal tracking.
- **Hybrid Retrieval**: Combines SQL `LIKE` filtering with vector cosine similarity reranking (0.7 semantic + 0.3 keyword weight).
- **Row-Level Security**: Resolves multi-tenant user boundaries via `get_user_scoped_query()`.

### `backend/embeddings.py`
Generates vector representations of code and text chunks.
- **Primary Model**: Local inference using `sentence-transformers/all-MiniLM-L6-v2` (384-dimensions).
- **Fallback Embeddings**: Deterministic SHA256-seeded random vectors (1536-dimensions) if the local PyTorch system fails to load.

### `backend/file_processor.py`
Text extraction and chunking pipeline for user document uploads.
- **Multi-Format Extraction**: Supports `.txt`, `.pdf`, `.docx`, `.csv`, `.py`, `.js`, etc.
- **Chunking Strategy**: Sentence-aware overlapping chunker (1000 character chunks with 100 character overlaps).
- **Database Loader**: Progressive Data Vault commits every 10 chunks to prevent memory bloat or timeouts.

### `backend/repo_scanner.py`
Handles remote repository cloning, branch analysis, and local folder scans.
- **Cloning Heuristic**: Shallow clones repository (`--depth 1`). Falls back to downloading repository zipball over GitHub APIs if git command-line tool is absent.
- **Exclusion Filters**: Ignores temporary directories, caches, and dependency folders (e.g., `.git`, `node_modules`, `venv`, `__pycache__`).
- **Jupyter Notebook Parser**: Concatenates code cell inputs while ignoring markdown text blocks.

---

## 3. Database Schema & Data Vault 2.0 Models

The relational database (`vault_v5.db`) uses SQLite with SQLAlchemy ORM. The tables are divided into three groups conforming to Data Vault 2.0 specifications.

### Hubs (Business Keys)
- **HubCode**: Natural keys representing unique blocks of parsed source code.
- **HubRepository**: Natural keys mapping registered GitHub and local paths.
- **HubUser**: Natural keys mapping registered users by unique email addresses.
- **HubDocument**: Natural keys representing file uploads.

### Links (Relationships)
- **LinkCodeRepository**: Maps parsed code blocks to their originating source code repository.
- **LinkUserRepository**: Scopes source code repositories to specific user IDs.
- **LinkUserDocument**: Scopes uploaded document keys to specific user IDs.

### Satellites (Context & Temporal History)
- **SatCodeContent**: Store code snippet texts, programming languages, and file path locations.
- **SatCodeMetrics**: Cyclomatic complexity estimates, line counts, and function parameter counts.
- **SatCodeEmbedding**: Multidimensional float vectors (JSON array) and the generating model.
- **SatDocumentContent**: Stores chunk raw texts, indexes, and dimensions.
- **SatDocumentEmbedding**: Stores chunk vector embeddings and metadata.
- **SatUserProfile**: Holds user settings, UI themes, and avatar details.

### Operational & Helper Tables
- **User**: Core table for authentication, lockout stats, and scan progression.
- **ChatMessage**: Stores conversational prompt history for UI chats.
- **SearchHistory**: Tracks past searches executed by users.
- **FileMetadata**: Tracks structural statistics of active files.
- **ScanJob**: Asynchronous ingestion jobs tracking active operations.
- **KeyPool**: Managed pool of LLM API keys.

---

## 4. Key Design Patterns

1. **Insert-Only Data Vault**: Modifying code structures doesn't write updates; it inserts new records with metadata timestamps and updates references, maintaining a lossless audit trail.
2. **Deterministic-to-LLM Routing**: Pre-calculates target intents via keyword arrays to avoid LLM tokens for obvious routing.
3. **Pluggable Embedding Fallback**: Ensures system startup succeeds even on resource-constrained servers without GPU support.
4. **Tenant Isolation**: Row-level filters (`user_id`) wrapper applied to every select statement.
