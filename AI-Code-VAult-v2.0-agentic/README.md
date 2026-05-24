<p align="center">
  <h1 align="center">🧠 AI Code Vault 2.0</h1>
  <p align="center">
    <strong>Enterprise-Grade, AI-Powered Code Intelligence Platform</strong>
  </p>
  <p align="center">
    Scan repositories. Embed knowledge. Query with agents. Ship smarter.
  </p>
  <p align="center">
    <a href="#-quick-start"><img src="https://img.shields.io/badge/version-2.5.9-00f2ff?style=for-the-badge&labelColor=0d1117" alt="Version 2.5.9"></a>&nbsp;
    <a href="https://www.python.org/downloads/release/python-3110/"><img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=0d1117" alt="Python 3.11"></a>&nbsp;
    <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/Streamlit-1.32-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white&labelColor=0d1117" alt="Streamlit"></a>&nbsp;
    <a href="#-license"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge&labelColor=0d1117" alt="License MIT"></a>
  </p>
</p>

<br>

AI Code Vault 2.0 is a **Multi-Agent RAG** (Retrieval-Augmented Generation) platform that transforms how teams understand, search, and interact with codebases. Clone any GitHub repository or upload files, and the platform chunks, embeds, and indexes every piece of code into a **Data Vault 2.0** warehouse — then lets you query it through **10 specialist AI agents** powered by Groq's blazing-fast LLM inference.

---

## ✨ Core Features

### 🔍 Repository Scanning & Ingestion
Clone and index entire GitHub repositories or local directories. Code is intelligently chunked into searchable, vector-embedded snippets with full metadata extraction — function signatures, class hierarchies, line counts, and cyclomatic complexity — all visualized through a real-time **Neural Stream Terminal** during ingestion.

### 📂 Multi-Format File Processing
Upload and process files across **14 supported formats**:

`PY` · `JS` · `TS` · `JSX` · `TSX` · `HTML` · `CSS` · `MD` · `JSON` · `SQL` · `PDF` · `DOCX` · `TXT` · `CSV`

### 🧬 Hybrid Semantic Search
A two-stage retrieval pipeline combining **SQL LIKE keyword filtering** with **cosine similarity reranking** using sentence-transformer embeddings. Final relevance scores blend semantic (70%) and keyword (30%) signals for precise, context-aware results.

### 🤖 Agentic AI Studio — 10 Specialist Agents

| Agent | Role |
|:------|:-----|
| **🎯 Supervisor** | Intelligent router — classifies intent and delegates to the right specialist |
| **📚 RAG Q&A** | Answers questions grounded in your indexed codebase via retrieval-augmented generation |
| **🧩 Quiz** | Generates interactive quizzes to test understanding of scanned code |
| **🔬 Extract** | Pulls structured data — functions, classes, imports, dependencies — from code chunks |
| **📊 Analysis** | Deep-dives into code quality, architecture patterns, and design decisions |
| **🩹 Patch Generator** | Produces unified diffs for suggested code modifications |
| **🔎 Code Reviewer** | Performs automated code reviews with actionable feedback |
| **🧪 Test Strategist** | Designs test plans, suggests edge cases, and outlines coverage strategies |
| **📝 Documentation** | Generates docstrings, README sections, and API documentation from code |
| **💬 General Chat** | Free-form conversation for questions outside the codebase context |

### 🏗️ Vault Explorer
Browse indexed code hubs and drill into satellite metadata — lines of code, cyclomatic complexity, parameter counts, and temporal history — all powered by the Data Vault 2.0 architecture underneath.

### 📈 Analytics Portal
Manage indexed files, visualize usage analytics with interactive charts, review past queries and feedback, and monitor system performance metrics at a glance.

### 🎨 User Profile & Theming
Configure your visual experience with three premium themes, manage passwords, and track personal usage statistics.

### 🛡️ Admin Dashboard
A full administrative control plane: global metrics, API key pool management (Groq & OpenRouter), user administration, activity audit logs, and built-in accuracy and scale test runners.

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit Frontend                       │
│          Glassmorphism UI · Three Themes · Mobile Ready          │
├─────────────────────────────────────────────────────────────────┤
│                     Supervisor Agent (Router)                    │
│            Intent Classification → Agent Delegation              │
├────┬────┬────┬────┬────┬────┬────┬────┬────┬────────────────────┤
│ RAG│Quiz│Ext │Anly│Ptch│Revw│Test│Docs│Chat│  Specialist Agents  │
├────┴────┴────┴────┴────┴────┴────┴────┴────┴────────────────────┤
│              Hybrid Search (Keyword + Semantic)                  │
│         SQL LIKE Filter → Cosine Similarity Reranking            │
├─────────────────────────────────────────────────────────────────┤
│                   Embedding Layer                                │
│            sentence-transformers (all-MiniLM-L6-v2)              │
├─────────────────────────────────────────────────────────────────┤
│                  Data Vault 2.0 Warehouse                        │
│     SQLite · 22 Models · 4 Views · Hub/Link/Satellite            │
│     Insert-Only History · Hash Change Detection · PIT Queries    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Vault 2.0 Methodology
The persistence layer follows the **Data Vault 2.0** standard — a proven enterprise data warehousing pattern:

- **Hubs** — Business keys for core entities (users, repositories, files, code chunks)
- **Links** — Relationships between hubs (user↔repo, repo↔file, file↔chunk)
- **Satellites** — Temporal, insert-only attribute records with hash-based change detection
- **Point-in-Time Queries** — Reconstruct the exact state of any entity at any moment in history
- **22 ORM models + 4 SQL views** backed by SQLite (`vault_v5.db`)

---

## 🔐 Authentication & Security

| Feature | Detail |
|:--------|:-------|
| Password Hashing | **bcrypt** with automatic salt generation |
| Session Tokens | Cookie-based, **7-day** expiry |
| Rate Limiting | **5 login attempts** per 15-minute window, then lockout |
| Admin Provisioning | First user matching `ADMIN_EMAIL` is auto-promoted; auto-created on empty DB |
| Role Model | Two roles — **Admin** (full control) and **User** (standard access) |

---

## 🎨 Design System

A premium **glassmorphism** aesthetic with `backdrop-filter: blur()` frosted-glass panels, animated floating background orbs, and gradient buttons with hover-lift transitions.

| Element | Specification |
|:--------|:-------------|
| **Typography** | Outfit (headings) + Inter (body) — Google Fonts |
| **Dark Theme** | Cyan accent `#00f2ff` on deep backgrounds |
| **Light Theme** | Blue accent `#006dff` on clean surfaces |
| **System Theme** | Auto-detects OS preference |
| **Layout** | Fully mobile-responsive |
| **Animations** | Floating orbs, gradient shifts, Neural Stream Terminal progress |

---

## 🚀 Quick Start

### Prerequisites
- Python **3.11+**
- A [Groq API key](https://console.groq.com/) (free tier available)

### Installation

```bash
# 1 — Clone the repository
git clone https://github.com/LibaMak/AI-Code-Vault-V2.0.git
cd AI-Code-Vault-V2.0

# 2 — Install dependencies
pip install -r requirements.txt

# 3 — Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY (at minimum)

# 4 — Launch the platform
streamlit run streamlit_app.py

# 5 — Open in your browser
# → http://localhost:8501
```

> **First Launch:** If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set in `.env`, an admin account is auto-provisioned on the empty database. Otherwise, the first registered user receives standard permissions.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GROQ_API_KEY` | — | **Required.** Groq API key for LLM inference |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Primary LLM model for agent reasoning |
| `GROQ_FAST_MODEL` | `llama-3.1-8b-instant` | Fast model for intent routing and output parsing |
| `DATABASE_URL` | `sqlite:///./vault_v5.db` | SQLAlchemy database connection string |
| `LOCAL_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model for vector embeddings |
| `ADMIN_EMAIL` | — | Email address for the auto-provisioned admin account |
| `ADMIN_PASSWORD` | — | Password for the auto-provisioned admin account |

---

## 📦 Dependencies

```text
streamlit==1.32             pandas==2.2.1             numpy==1.26.4
groq==0.18.0                sqlalchemy==2.0.28        sentence-transformers==2.5.1
scikit-learn==1.5.2         PyPDF2==3.0.1             python-docx==1.1.0
bcrypt==4.1.2               GitPython==3.1.42         streamlit-authenticator==0.3.2
streamlit-lottie            extra-streamlit-components watchdog
```

Full list in [`requirements.txt`](requirements.txt).

---

## 🗂️ Project Structure

```
AI-Code-Vault-v2.0-agentic/
│
├── streamlit_app.py              # Main application — UI routing & orchestration
│
├── backend/
│   ├── __init__.py               # Package init, exports version 2.5.9
│   ├── agent.py                  # Multi-agent orchestration (Supervisor + 9 specialists)
│   ├── ai_parser.py              # Code parsing — AST extraction + LLM enrichment
│   ├── db_connector.py           # Data Vault 2.0 ORM — 22 models, 4 views, SQLAlchemy
│   ├── embeddings.py             # Embedding provider — sentence-transformers wrapper
│   ├── file_processor.py         # File upload handler & text extraction (PDF, DOCX, etc.)
│   └── repo_scanner.py           # Git repo cloning, file walking & code chunking
│
├── .streamlit/
│   └── config.toml               # Streamlit theme & server configuration
│
├── .devcontainer/                # GitHub Codespaces / DevContainer setup
│   └── devcontainer.json         # Python 3.11 (Debian Bookworm), auto-start on :8501
│
├── requirements.txt              # Pinned Python dependencies
├── .env.example                  # Environment variable template
└── vault_v5.db                   # SQLite database (created on first run)
```

---

## 👥 User Roles

### Admin
Full platform control — global metrics dashboard, user management, API key pool configuration (Groq & OpenRouter), activity audit logs, and built-in accuracy and scale test runners.

### User
Standard access — scan repositories, upload files, search the vault, interact with all 10 AI agents, view personal analytics, and configure profile and theme preferences.

---

## 🐳 DevContainer

A pre-configured development environment for **GitHub Codespaces** and VS Code Remote Containers:

- **Base image:** Python 3.11 on Debian Bookworm
- **Auto-start:** Streamlit launches automatically on port **8501**
- **Zero config:** Dependencies install on container creation

---

## 🏗️ Built With

| Technology | Purpose |
|:-----------|:--------|
| [**Streamlit**](https://streamlit.io/) | Interactive web application framework |
| [**Groq**](https://groq.com/) | Ultra-fast LLM inference (Llama 3.3-70B & 3.1-8B) |
| [**SQLAlchemy**](https://www.sqlalchemy.org/) | ORM and database toolkit |
| [**SQLite**](https://www.sqlite.org/) | Embedded relational database |
| [**sentence-transformers**](https://www.sbert.net/) | Semantic embedding generation (all-MiniLM-L6-v2) |
| [**scikit-learn**](https://scikit-learn.org/) | Cosine similarity computation for search reranking |
| [**GitPython**](https://gitpython.readthedocs.io/) | Git repository cloning and management |
| [**PyPDF2**](https://pypdf2.readthedocs.io/) | PDF text extraction |
| [**python-docx**](https://python-docx.readthedocs.io/) | DOCX document parsing |
| [**bcrypt**](https://github.com/pyca/bcrypt) | Secure password hashing |

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024–2026 AI Code Vault Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

<p align="center">
  <sub>Built with 🧠 and ☕ — AI Code Vault 2.0 · v2.5.9</sub>
</p>
