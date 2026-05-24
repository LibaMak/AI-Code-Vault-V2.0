# Changelog

All notable changes to **AI Code Vault 2.0** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.5.9] — 2026-05-24

### Added

- **Multi-Agent RAG System** — 10 specialist agents orchestrated by a Supervisor agent:
  Supervisor, RAG Q&A, Patch Generator, Code Reviewer, Test Strategist,
  Documentation, Quiz, Extract, Analysis, and General Chat.
- **Data Vault 2.0 Database Architecture** — Hub / Link / Satellite methodology for
  scalable, auditable data storage.
- **Hybrid Semantic Search** — SQL `LIKE` filtering combined with cosine-similarity
  reranking for high-precision code retrieval.
- **Three-Theme System** — Dark, Light, and System themes powered by CSS custom
  properties with user-preference persistence.
- **Premium Glassmorphism UI** — Frosted-glass design language with animated
  background orbs and smooth transitions.
- **Cookie-Based Persistent Sessions** — Secure session tokens with 7-day expiry and
  automatic renewal.
- **Rate-Limited Login** — Brute-force protection with a 5-attempt limit and 15-minute
  lockout window.
- **Password Strength Validation** — Enforces minimum 8 characters with uppercase,
  lowercase, digit, and special-character requirements.
- **Admin Dashboard** — Global metrics overview and API key pool management for
  administrators.
- **Accuracy & Scale Test Runners** — Automated evaluation harnesses for measuring
  system accuracy and throughput under load.
- **Neural Stream Terminal** — Real-time progress visualization for long-running agent
  operations.
- **Agent Matrix Discovery Panel** — Sidebar panel for exploring available agents, their
  capabilities, and current status.
- **File Upload Support** — Ingest 14 file types: PY, JS, TS, JSX, TSX, HTML, CSS, MD,
  JSON, SQL, PDF, DOCX, TXT, and CSV.
- **GitHub Repository Scanning** — Index public and private repositories via shallow
  clone with automatic ZIP-archive fallback.
- **Jupyter Notebook Support** — Parse and index `.ipynb` files including code cells,
  markdown cells, and outputs.
- **User Profile** — Per-user settings with theme persistence backed by Data Vault 2.0
  satellites.
- **Analytics Portal** — Usage charts, performance metrics, and trend visualization for
  monitoring system health.
- **Vault Explorer** — Interactive browser for navigating indexed code hubs and their
  associated metadata.
- **Search Feedback System** — Thumbs-up / thumbs-down feedback loop on search results
  to improve retrieval quality.
- **Patch File Generation** — Export agent-suggested code changes as unified diff patch
  files.
- **ZIP Export** — Download indexed vault content and GitHub repository snapshots as
  compressed archives.
- **Database Self-Healing** — Automatic corruption detection and recovery routines for
  the Data Vault store.
- **Mobile Responsive Design** — Fully responsive layouts optimized for tablet and
  mobile viewports.
- **DevContainer Support** — First-class GitHub Codespaces and VS Code DevContainer
  configuration for one-click development environments.

### Security

- **bcrypt Password Hashing** — All passwords hashed with per-user salt using bcrypt.
- **XSRF Protection** — Cross-site request forgery tokens enabled on all state-changing
  endpoints.
- **Row-Level Data Isolation** — Strict tenant separation ensures users can only access
  their own data.
- **Admin Auto-Provisioning** — Admin account bootstrapped securely from environment
  variables on first launch.
- **Secure Cookie Storage** — Session tokens stored in `HttpOnly`, `SameSite` cookies
  with configurable `Secure` flag.
