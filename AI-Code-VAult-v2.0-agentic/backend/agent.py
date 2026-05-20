# backend/agent.py
"""Multi-agent layer for AI Code Vault 2.0.

This module exposes ``run_agent(user_message, chat_history, backend)`` for the
Streamlit UI.  It implements a small agentic team:

- SupervisorAgent: routes the user request and coordinates other agents.
- RAGAnswerAgent: answers questions with retrieval-augmented generation.
- PatchDiffGenerator: generates unified diffs/patches for indexed vault snippets and can apply them on request.
- CodeReviewerAgent: reviews code for quality, security, and performance.
- TestStrategistAgent: suggests tests and validation plans.
- DocumentationAgent: creates summaries, docs, and onboarding notes.

The editor intentionally edits the *indexed vault copy* only. It does not write
back to a remote GitHub repository. Returned patches can be copied into a real
repo, and an explicit "apply/save/update the vault" request can update the
matching Hub.code_snippet in the local database.
"""

from __future__ import annotations

import ast
import difflib
import io
import json
import os
import re
import zipfile
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import urlopen
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy.orm import Session
import traceback
from repo_scanner import get_repo_chunks, _log_debug
from ai_parser import parse_code_chunk
from embeddings import get_embeddings
from db_connector import get_engine, Hub, ScanJob

# Load .env from project root so GROQ_API_KEY is available when running Streamlit.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
MAX_CONTEXT_CHARS = 9000

_client_cache: Dict[str, Groq] = {}


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    answer: str
    steps: List[dict]
    tools_used: List[str]
    active_agent: str
    artifacts: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "steps": self.steps,
            "tools_used": self.tools_used,
            "active_agent": self.active_agent,
            "artifacts": self.artifacts or {},
        }


def _extract_retry_hint(error_text: str) -> str:
    marker = "Please try again in "
    if marker in error_text:
        return error_text.split(marker, 1)[1].split(".", 1)[0].strip()
    return "a few minutes"


def _build_provider_fallback(user_message: str, error_text: str) -> str:
    if "rate_limit_exceeded" in error_text or "Error code: 429" in error_text:
        return (
            "The AI provider is currently rate-limited. Please try again in "
            f"{_extract_retry_hint(error_text)}."
        )
    if "model_decommissioned" in error_text or "Error code: 400" in error_text:
        return "The configured AI model is unavailable. Set GROQ_MODEL to a supported model and retry."
    return "I could not reach the AI provider just now. Please retry shortly."


def _resolve_api_key(backend: Optional[dict] = None) -> Optional[str]:
    """Resolve an API key from env first, then the app's Admin KeyPool if present."""
    if backend:
        backend_key = backend.get("groq_api_key")
        if isinstance(backend_key, str) and backend_key.strip() and backend_key.strip() != "your_groq_api_key_here":
            return backend_key.strip()

    key = os.getenv("GROQ_API_KEY")
    if key and key.strip() and key.strip() != "your_groq_api_key_here":
        return key.strip()

    if not backend:
        return None

    # Optional fallback to the application's global KeyPool table.
    try:
        KeyPool = backend.get("KeyPool")
        get_engine = backend.get("get_engine")
        if not KeyPool or not get_engine:
            return None
        with Session(get_engine()) as s:
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


def get_client(backend: Optional[dict] = None) -> Optional[Groq]:
    api_key = _resolve_api_key(backend)
    if not api_key:
        return None
    if api_key not in _client_cache:
        _client_cache[api_key] = Groq(api_key=api_key)
    return _client_cache[api_key]


def _safe_json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        # Try to recover fenced JSON.
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                pass
    return default


def _call_llm(
    backend: dict,
    messages: List[dict],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> str:
    client = get_client(backend)
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not configured and no active GROQ key exists in Admin KeyPool.")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def _run_search(backend: dict, query: str, top_k: int = 5) -> List[dict]:
    search_fn = backend.get("run_hybrid_search") or backend.get("search_vault")
    if not callable(search_fn):
        return []
    
    # Try calling as database connector function: run_hybrid_search(session, query, user_id, top_k=5)
    get_engine = backend.get("get_engine")
    user_id = backend.get("current_user_id")
    if get_engine and user_id is not None:
        try:
            with Session(get_engine()) as session:
                # Import here to avoid any issues
                import db_connector
                results = db_connector.run_hybrid_search(session, query, user_id, top_k=top_k)
                return _normalize_search_results(results, top_k)
        except Exception as e:
            # Fallback to single parameter call
            pass

    try:
        results = search_fn(query, top_k=top_k)
    except TypeError:
        results = search_fn(query)
    except Exception as exc:
        return [{"name": "search_error", "snippet": str(exc), "score": 0}]

    return _normalize_search_results(results, top_k)


def _normalize_search_results(results: List[Any], top_k: int) -> List[dict]:
    normalized: List[dict] = []
    for item in results or []:
        if isinstance(item, dict):
            normalized.append(
                {
                    "name": item.get("name") or item.get("filename") or item.get("source") or "unknown",
                    "snippet": item.get("snippet") or item.get("content") or item.get("chunk") or "",
                    "score": item.get("score") or item.get("similarity") or 0,
                }
            )
        else:
            normalized.append({"name": "unknown", "snippet": str(item), "score": 0})
    return normalized[:top_k]


def _format_sources(results: List[dict], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    chunks: List[str] = []
    used = 0
    for i, r in enumerate(results, 1):
        text = str(r.get("snippet", ""))
        entry = f"[Source {i}] {r.get('name', 'unknown')} | score={r.get('score', 0)}\n{text}\n"
        if used + len(entry) > max_chars:
            entry = entry[: max(0, max_chars - used)]
        chunks.append(entry)
        used += len(entry)
        if used >= max_chars:
            break
    return "\n".join(chunks)


def _source_list(results: List[dict]) -> str:
    names = []
    for r in results:
        n = str(r.get("name", "unknown"))
        if n not in names:
            names.append(n)
    return ", ".join(names) if names else "none"


def _wants_apply(message: str) -> bool:
    text = message.lower()
    return any(phrase in text for phrase in ["apply", "save", "update vault", "write the edit", "commit edit"])


def _build_unified_diff(filename: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def _update_indexed_snippet(backend: dict, hub_name: str, new_code: str) -> Tuple[bool, str]:
    """Update a Hub.code_snippet by hash_key/name in the local vault DB.

    If streamlit_app.py provides backend["current_user_id"], the update is scoped
    to that user to avoid cross-account changes when hub names collide.
    """
    Hub = backend.get("Hub")
    get_engine = backend.get("get_engine")
    if not Hub or not get_engine:
        return False, "Database backend is unavailable."
    try:
        with Session(get_engine()) as s:
            query = s.query(Hub).filter(Hub.hash_key == hub_name)
            current_user_id = backend.get("current_user_id")
            if current_user_id is not None and hasattr(Hub, "user_id"):
                query = query.filter(Hub.user_id == current_user_id)
            hub = query.first()
            if not hub:
                return False, f"No indexed hub named '{hub_name}' was found for the active user."
            hub.code_snippet = new_code
            s.commit()
        return True, f"Updated indexed vault snippet: {hub_name}"
    except Exception as exc:
        return False, f"Could not update indexed snippet: {exc}"




def _heuristic_edit(user_message: str, old_code: str) -> Optional[Tuple[str, str, List[str]]]:
    """Small deterministic editor used when the LLM is unavailable/rate-limited.

    This is intentionally conservative. It only applies obvious text-level edits
    for common requests so the PatchDiffGenerator can still produce a useful diff
    during provider outages.
    """
    text = user_message.lower()
    new_code = old_code
    notes = ["Used deterministic fallback editing because the LLM provider was unavailable or rate-limited."]

    if "login" in text and "error" in text and any(k in text for k in ["clear", "clearer", "improve", "better"]):
        replacements = {
            'Explicit Warning: Password match error or User not found!': (
                'Login failed. Check your email and password, or create a new account if you have not registered yet.'
            ),
            'Password match error or User not found!': (
                'Login failed. Check your email and password, or create a new account if you have not registered yet.'
            ),
            'User not found': 'Login failed. Check your email and password, then try again.',
        }
        for old, new in replacements.items():
            new_code = new_code.replace(old, new)
        if new_code != old_code:
            return "Improved the login failure message while avoiding sensitive authentication details.", new_code, notes

    if "todo" in text and "comment" in text:
        new_code = old_code + "\n# TODO: Review this section based on the requested change.\n"
        return "Added a TODO comment for follow-up review.", new_code, notes

    if any(k in text for k in ["package", "__init__.py", "init file", "initializer"]):
        if "__version__" in old_code and "__all__" not in old_code:
            new_code = old_code.rstrip() + "\n\n__all__ = [\"__version__\"]\n"
            notes.append("Added a minimal export list for package initialization.")
            return "Improved the package initializer with a minimal export list.", new_code, notes

    return None


def _sanitize_zip_entry(name: str) -> str:
    """Convert a hub name/path into a safe zip entry name."""
    cleaned = (name or "snippet").strip().replace("\\", "/")
    cleaned = re.sub(r"[^A-Za-z0-9._/\-]", "_", cleaned)
    cleaned = cleaned.lstrip("/")
    if not cleaned:
        return "snippet.txt"
    if "/" not in cleaned and "." not in cleaned:
        cleaned += ".txt"
    return cleaned


def _extract_github_repo_url(text: str) -> Optional[str]:
    """Extract the first GitHub repository URL from free-form text."""
    m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", text)
    if not m:
        return None
    url = m.group(0)
    if url.endswith(".git"):
        url = url[:-4]
    return url


def _repo_slug_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    raise ValueError("Invalid GitHub repository URL.")


def _download_github_zip(repo_url: str) -> bytes:
    """Download a repository archive from GitHub as zip bytes."""
    slug = _repo_slug_from_url(repo_url)
    # zipball resolves to the default branch and works for public repositories.
    zipball_url = f"https://api.github.com/repos/{slug}/zipball"
    with urlopen(zipball_url, timeout=45) as resp:  # nosec B310 - controlled GitHub API endpoint
        return resp.read()


def _build_indexed_repo_zip(backend: dict, repo_url: str) -> Tuple[Optional[bytes], int]:
    """Build a zip from indexed snippets for a repo, preserving post-edit vault state."""
    Hub = backend.get("Hub")
    get_engine = backend.get("get_engine")
    user_id = backend.get("current_user_id")
    if not Hub or not get_engine or not user_id:
        return None, 0

    slug = _repo_slug_from_url(repo_url)
    search_terms = [repo_url, slug, slug.split("/")[-1]]

    with Session(get_engine()) as s:
        query = s.query(Hub).filter(Hub.user_id == user_id)
        hubs = query.all()

    matched = []
    for hub in hubs:
        ru = str(getattr(hub, "repo_url", "") or "")
        if any(t and t in ru for t in search_terms):
            matched.append(hub)

    # Fallback: if repo_url metadata does not preserve original GitHub URL,
    # derive an export set from vault retrieval for this repo query.
    if not matched:
        retrieved = _run_search(backend, repo_url, top_k=30)
        if not retrieved:
            return None, 0
        seen_names = set()
        pseudo_rows = []
        for item in retrieved:
            name = str(item.get("name") or "snippet")
            if name in seen_names:
                continue
            seen_names.add(name)
            pseudo_rows.append({
                "hash_key": name,
                "code_snippet": str(item.get("snippet") or ""),
            })

        if not pseudo_rows:
            return None, 0

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest = [
                "AI Code Vault Indexed Snapshot (Search Fallback)",
                f"Generated UTC: {datetime.utcnow().isoformat()}Z",
                f"Repo URL: {repo_url}",
                f"Entries: {len(pseudo_rows)}",
                "",
                "Files:",
            ]
            for i, row in enumerate(pseudo_rows, 1):
                name = _sanitize_zip_entry(str(row.get("hash_key") or f"snippet_{i}.txt"))
                content = str(row.get("code_snippet") or "")
                zf.writestr(name, content)
                manifest.append(f"{i}. {name}")
            zf.writestr("MANIFEST.txt", "\n".join(manifest) + "\n")

        return buf.getvalue(), len(pseudo_rows)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = [
            "AI Code Vault Indexed Snapshot",
            f"Generated UTC: {datetime.utcnow().isoformat()}Z",
            f"Repo URL: {repo_url}",
            f"Entries: {len(matched)}",
            "",
            "Files:",
        ]
        for i, hub in enumerate(matched, 1):
            name = _sanitize_zip_entry(str(getattr(hub, "hash_key", "") or f"snippet_{i}.txt"))
            content = str(getattr(hub, "code_snippet", "") or "")
            zf.writestr(name, content)
            manifest.append(f"{i}. {name}")
        zf.writestr("MANIFEST.txt", "\n".join(manifest) + "\n")

    return buf.getvalue(), len(matched)


# ---------------------------------------------------------------------------
# Agent implementations
# ---------------------------------------------------------------------------

def _is_valid_python(code: str) -> bool:
    """Return True if code parses as valid Python. Non-Python content returns True (skip validation)."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


class BaseVaultAgent:
    name = "BaseAgent"
    description = "Base vault agent"

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        raise NotImplementedError


class RAGAnswerAgent(BaseVaultAgent):
    name = "RAGAnswerAgent"
    description = "Answers questions using retrieved vault context."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["search_vault"]
        results = _run_search(backend, user_message, top_k=8)
        steps.append({"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} vault chunk(s)."})

        if not results:
            return AgentResult(
                answer="No relevant content found in your vault for this query",
                steps=steps,
                tools_used=tools,
                active_agent=self.name,
            )

        context = _format_sources(results)
        try:
            answer = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a precise RAG engineering assistant. Answer only from the provided vault context. "
                            "If evidence is missing, say what is missing. You MUST explicitly cite the source filename and approximate location for every claim you make inline."
                        ),
                    },
                    {"role": "user", "content": f"Question:\n{user_message}\n\nVault context:\n{context}"},
                ],
                temperature=0.15,
            )
        except Exception as exc:
            steps.append({"type": "fallback", "content": str(exc)})
            answer = (
                "I found relevant vault context, but the LLM is unavailable. Here are the top retrieved sources:\n\n"
                + "\n\n".join(f"- **{r['name']}** (score {r['score']}): {r['snippet'][:500]}" for r in results[:3])
            )

        sources_list = [r.get("name") for r in results if r.get("name") and r.get("name") != "unknown"]
        unique_sources = list(dict.fromkeys(sources_list))
        if unique_sources:
            footer = "\n\n### Sources Referenced:\n" + "\n".join(f"- {s}" for s in unique_sources)
        else:
            footer = "\n\n### Sources Referenced:\n- vault context"
            
        if "Sources Referenced" not in answer:
            answer += footer

        return AgentResult(answer=answer, steps=steps, tools_used=tools, active_agent=self.name)


class QuizAgent(BaseVaultAgent):
    name = "QuizAgent"
    description = "Generates a 5-question quiz from vault context."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        results = _run_search(backend, user_message, top_k=6)
        if not results:
            return AgentResult(
                answer="No vault content found to generate a quiz. Please ingest a repository or document first.",
                steps=[],
                tools_used=["search_vault", "generate_quiz"],
                active_agent=self.name,
            )
        
        context = _format_sources(results)
        steps = [
            {"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} chunks for quiz context."},
            {"type": "tool_result", "tool": "format_sources", "content": f"Formatted context ({len(context)} chars)."}
        ]
        
        try:
            raw = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a quiz generator. Based ONLY on the provided vault context, "
                            "generate exactly 5 questions: 3 multiple choice (4 options each) and "
                            "2 True/False. Return ONLY a JSON array. Each object must have these "
                            "exact keys: question (string), type (either 'mcq' or 'tf'), options "
                            "(list of strings, 4 for mcq, ['True','False'] for tf), correct_index "
                            "(integer 0-3), explanation (string). No other text outside the JSON."
                        )
                    },
                    {"role": "user", "content": f"Topic/Query: {user_message}\n\nVault Context:\n{context}"}
                ],
                max_tokens=1500
            )
            
            # Post-process JSON
            json_str = raw.strip()
            fence_match = re.search(r"```(?:json)?\s*(.*?)```", json_str, re.DOTALL | re.IGNORECASE)
            if fence_match:
                json_str = fence_match.group(1).strip()
            
            try:
                parsed = json.loads(json_str)
                if not isinstance(parsed, list):
                    raise ValueError("JSON is not a list")
                
                md_lines = []
                letters = ["A", "B", "C", "D"]
                for i, q in enumerate(parsed, 1):
                    qtype = q.get("type", "mcq")
                    question_text = q.get("question", "No question text")
                    options = q.get("options", [])
                    correct_idx = q.get("correct_index", 0)
                    explanation = q.get("explanation", "")
                    
                    md_lines.append(f"**Question {i}:** {question_text}")
                    if qtype == "mcq":
                        opts_str = "  ".join(f"{letters[j]}) {opt}" for j, opt in enumerate(options[:4]))
                        md_lines.append(opts_str)
                        correct_opt = options[correct_idx] if correct_idx < len(options) else "Unknown"
                        md_lines.append(f"✓ Correct: {correct_opt}")
                    else:  # True/False
                        correct_opt = options[correct_idx] if correct_idx < len(options) else "True"
                        md_lines.append(f"✓ {correct_opt}")
                    
                    md_lines.append(f"*{explanation}*")
                    md_lines.append("")
                
                answer = "\n".join(md_lines)
            except Exception:
                answer = f"Quiz generation (raw format):\n\n{raw}"
                
        except Exception as e:
            answer = f"Quiz generation (raw format):\n\nFailed to call LLM: {e}"
            
        return AgentResult(
            answer=answer,
            steps=steps,
            tools_used=["search_vault", "generate_quiz"],
            active_agent=self.name
        )


class ExtractAgent(BaseVaultAgent):
    name = "ExtractAgent"
    description = "Extracts tables or key points from vault context."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        results = _run_search(backend, user_message, top_k=6)
        if not results:
            return AgentResult(
                answer="No vault content found to extract from. Please ingest content first.",
                steps=[],
                tools_used=["search_vault", "extract_content"],
                active_agent=self.name,
            )
        
        context = _format_sources(results)
        steps = [
            {"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} chunks for extraction."},
            {"type": "tool_result", "tool": "format_sources", "content": f"Formatted context ({len(context)} chars)."}
        ]
        
        try:
            answer = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a content extractor. Analyze the provided vault context. "
                            "If the content contains naturally tabular data (parameters, configs, "
                            "comparisons, lists of items with attributes) return a single Markdown "
                            "table. Otherwise return structured bullet points with a one-line bold "
                            "header. Choose ONE format only — never both in the same response. "
                            "Maximum 20 rows for tables, 15 bullets for lists. Be concise."
                        )
                    },
                    {"role": "user", "content": f"Extract Request: {user_message}\n\nVault Context:\n{context}"}
                ],
                max_tokens=1000
            )
        except Exception:
            answer = "Extraction unavailable. Sources: " + _source_list(results)
            
        return AgentResult(
            answer=answer,
            steps=steps,
            tools_used=["search_vault", "extract_content"],
            active_agent=self.name
        )


class AnalysisAgent(BaseVaultAgent):
    name = "AnalysisAgent"
    description = "Performs architectural analysis and pattern identification."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        results = _run_search(backend, user_message, top_k=8)
        if not results:
            return AgentResult(
                answer="No vault content found for analysis. Please ingest a repository first.",
                steps=[],
                tools_used=["search_vault", "analyze_architecture"],
                active_agent=self.name,
            )
        
        context = _format_sources(results)
        steps = [
            {"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} chunks for analysis."},
            {"type": "tool_result", "tool": "format_sources", "content": f"Formatted context ({len(context)} chars)."}
        ]
        
        try:
            answer = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "You are an architectural analyst. Analyze the provided codebase "
                            "context at the SYSTEM and DESIGN level — not line-level bugs. "
                            "Your response must have exactly three sections with these headers:\n"
                            "## Patterns Found\n"
                            "List design patterns present in the code with evidence.\n"
                            "## Anti-Patterns & Weaknesses\n"
                            "List architectural weaknesses with specific file/function references "
                            "from the vault context.\n"
                            "## Recommendations\n"
                            "Give exactly 3-5 actionable recommendations. Label each with priority: "
                            "🔴 High, 🟡 Medium, or 🟢 Low. Reference actual filenames from context."
                        )
                    },
                    {"role": "user", "content": f"Analysis Request: {user_message}\n\nVault Context:\n{context}"}
                ],
                max_tokens=2000
            )
        except Exception:
            answer = "Analysis unavailable. Sources: " + _source_list(results)
            
        return AgentResult(
            answer=answer,
            steps=steps,
            tools_used=["search_vault", "analyze_architecture"],
            active_agent=self.name
        )


class PatchDiffGenerator(BaseVaultAgent):
    name = "PatchDiffGenerator"
    description = "Generates unified diffs/patches for indexed vault snippets and can apply them to the local vault on request."

    # ------------------------------------------------------------------
    # Step 1 — File selector: LLM picks the most relevant result.
    # ------------------------------------------------------------------
    def _select_target(self, results: List[dict], user_message: str, backend: dict) -> dict:
        file_list = "\n".join(f"[{i}] {r.get('name', 'unknown')}" for i, r in enumerate(results))
        try:
            raw = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": "Select the most relevant file to edit. Return ONLY the 0-based index number — nothing else.",
                    },
                    {
                        "role": "user",
                        "content": f"User request:\n{user_message}\n\nFiles:\n{file_list}",
                    },
                ],
                model=FAST_MODEL,
                temperature=0,
                max_tokens=10,
            )
            idx = int(raw.strip())
            if 0 <= idx < len(results):
                return results[idx]
        except Exception:
            pass
        return results[0]

    # ------------------------------------------------------------------
    # Step 2 — Plan: describe exactly what needs to change.
    # ------------------------------------------------------------------
    def _plan_edit(self, code: str, user_message: str, backend: dict) -> str:
        return _call_llm(
            backend,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a senior software engineer. "
                        "Explain EXACTLY what needs to change in the code. Be precise and concise."
                    ),
                },
                {
                    "role": "user",
                    "content": f"User request:\n{user_message}\n\nCode:\n{code[:3000]}",
                },
            ],
            temperature=0.1,
            max_tokens=400,
        )

    # ------------------------------------------------------------------
    # Step 3 — Apply: return ONLY the updated code, no fences.
    # ------------------------------------------------------------------
    def _apply_edit(self, code: str, plan: str, backend: dict) -> str:
        return _call_llm(
            backend,
            [
                {
                    "role": "system",
                    "content": (
                        "You are modifying code. Apply the requested changes, keep everything else "
                        "unchanged, and return ONLY the updated code — no explanations, no markdown fences."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Plan:\n{plan}\n\nCode:\n{code}",
                },
            ],
            temperature=0.05,
            max_tokens=1800,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["search_vault", "select_target", "plan_edit", "apply_edit", "generate_patch"]

        # 1. Search vault
        results = _run_search(backend, user_message, top_k=5)
        steps.append({"type": "tool_call", "tool": "search_vault", "content": f"Located {len(results)} candidate snippet(s)."})
        if not results:
            return AgentResult(
                answer="I could not find an indexed file/snippet to edit. Ingest the target repo/file first or mention the exact hub/file name.",
                steps=steps,
                tools_used=tools,
                active_agent=self.name,
            )

        # 2. Select most relevant file
        target = self._select_target(results, user_message, backend)
        target_name = str(target.get("name", "unknown"))
        old_code = str(target.get("snippet", ""))
        steps.append({"type": "tool_result", "tool": "select_target", "content": f"Selected: {target_name}"})

        # 3. Plan the edit
        notes: List[str] = []
        try:
            plan = self._plan_edit(old_code, user_message, backend)
        except Exception as exc:
            steps.append({"type": "fallback", "content": f"Plan step failed: {exc}"})
            plan = user_message  # use raw request as plan
        steps.append({"type": "tool_result", "tool": "plan_edit", "content": f"Plan: {plan[:120]}..."})

        # 4. Apply the edit
        new_code = old_code
        try:
            new_code = self._apply_edit(old_code, plan, backend)
            steps.append({"type": "tool_result", "tool": "apply_edit", "content": "Edits applied."})
        except Exception as exc:
            steps.append({"type": "fallback", "content": f"Apply step failed: {exc}"})
            heuristic = _heuristic_edit(user_message, old_code)
            if heuristic:
                plan, new_code, notes = heuristic
            else:
                notes = [
                    "Configure GROQ_API_KEY or an active Admin KeyPool key, then retry.",
                    "If you just added a key in the UI, refresh the page so the active session picks it up.",
                ]

        # 5. Validate (Python files only)
        if new_code and new_code != old_code:
            looks_like_python = any(kw in old_code[:500] for kw in ["def ", "class ", "import ", "from "])
            if looks_like_python and not _is_valid_python(new_code):
                notes.append("⚠️ Generated code failed Python AST validation — review before applying.")

        # 6. Generate diff
        diff = _build_unified_diff(target_name, old_code, new_code) if new_code != old_code else ""
        steps.append({"type": "tool_result", "tool": "generate_patch", "content": f"Generated diff with {len(diff)} characters."})

        # 7. Optionally apply to vault
        apply_note = ""
        if _wants_apply(user_message) and diff:
            tools.append("update_indexed_snippet")
            ok, msg = _update_indexed_snippet(backend, target_name, new_code)
            steps.append({"type": "tool_result", "tool": "update_indexed_snippet", "content": msg})
            apply_note = f"\n\nVault update: {'✅' if ok else '⚠️'} {msg}"
        elif diff:
            apply_note = "\n\nI did not apply this automatically. Say **apply/save this edit** to update the indexed vault snippet."

        answer = f"### {self.name}: proposed edit for `{target_name}`\n\n**Plan:** {plan}\n"
        if notes:
            answer += "\nNotes:\n" + "\n".join(f"- {n}" for n in notes)
        if diff:
            answer += f"\n\n```diff\n{diff[:6000]}\n```"
        else:
            answer += "\n\nNo code changes were generated."
        answer += apply_note

        return AgentResult(
            answer=answer,
            steps=steps,
            tools_used=tools,
            active_agent=self.name,
            artifacts={"target": target_name, "diff": diff, "edited_code": new_code},
        )


class CodeReviewerAgent(BaseVaultAgent):
    name = "CodeReviewerAgent"
    description = "Performs code review, security, and performance analysis using vault context."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["search_vault", "review_code"]
        results = _run_search(backend, user_message, top_k=7)
        steps.append({"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} review target(s)."})
        context = _format_sources(results)
        try:
            answer = _call_llm(
                backend,
                [
                    {"role": "system", "content": "You are a senior code reviewer. Provide prioritized findings with severity, evidence, and fixes. Cite source names."},
                    {"role": "user", "content": f"Review request:\n{user_message}\n\nVault context:\n{context}"},
                ],
                temperature=0.15,
            )
        except Exception as exc:
            steps.append({"type": "fallback", "content": str(exc)})
            answer = "LLM review unavailable. Top candidate sources: " + _source_list(results)
        return AgentResult(answer=answer, steps=steps, tools_used=tools, active_agent=self.name)


class TestStrategistAgent(BaseVaultAgent):
    name = "TestStrategistAgent"
    description = "Creates tests, edge cases, and validation plans from retrieved code."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["search_vault", "design_tests"]
        results = _run_search(backend, user_message, top_k=6)
        steps.append({"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} chunks for test planning."})
        context = _format_sources(results)
        try:
            answer = _call_llm(
                backend,
                [
                    {"role": "system", "content": "You are a testing specialist. Create practical unit/integration tests and edge cases. Include example test code when possible."},
                    {"role": "user", "content": f"Testing request:\n{user_message}\n\nVault context:\n{context}"},
                ],
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as exc:
            steps.append({"type": "fallback", "content": str(exc)})
            answer = "Testing plan generation needs an LLM key. Retrieved sources: " + _source_list(results)
        return AgentResult(answer=answer, steps=steps, tools_used=tools, active_agent=self.name)


class DocumentationAgent(BaseVaultAgent):
    name = "DocumentationAgent"
    description = "Summarizes files/features and creates docs from vault context."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["search_vault", "write_docs"]
        results = _run_search(backend, user_message, top_k=8)
        steps.append({"type": "tool_call", "tool": "search_vault", "content": f"Retrieved {len(results)} documentation source(s)."})
        context = _format_sources(results)
        try:
            answer = _call_llm(
                backend,
                [
                    {"role": "system", "content": "You are a technical documentation agent. Produce clear markdown docs, summaries, or onboarding notes with source citations."},
                    {"role": "user", "content": f"Documentation request:\n{user_message}\n\nVault context:\n{context}"},
                ],
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as exc:
            steps.append({"type": "fallback", "content": str(exc)})
            answer = "Documentation generation needs an LLM key. Retrieved sources: " + _source_list(results)
        return AgentResult(answer=answer, steps=steps, tools_used=tools, active_agent=self.name)


class ZipExportAgent(BaseVaultAgent):
    name = "ZipExportAgent"
    description = "Exports a downloadable ZIP for a GitHub repo using latest indexed state when available."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["export_repo_zip"]
        repo_url = _extract_github_repo_url(user_message)

        if not repo_url:
            return AgentResult(
                answer=(
                    "Please include a GitHub repo URL in your request.\n\n"
                    "Example: Export ZIP for https://github.com/owner/repo"
                ),
                steps=steps,
                tools_used=tools,
                active_agent=self.name,
            )

        steps.append({"type": "tool_call", "tool": "export_repo_zip", "content": f"Preparing ZIP export for {repo_url}"})

        zip_bytes: Optional[bytes] = None
        zip_source = "indexed_vault"
        indexed_count = 0

        # Auto-select latest local state first so users do not need "before/after" phrasing.
        zip_bytes, indexed_count = _build_indexed_repo_zip(backend, repo_url)

        if zip_bytes is None:
            try:
                zip_bytes = _download_github_zip(repo_url)
                zip_source = "github"
            except Exception as exc:
                steps.append({"type": "fallback", "content": f"GitHub ZIP download failed: {exc}"})
                zip_bytes, indexed_count = _build_indexed_repo_zip(backend, repo_url)
                if zip_bytes:
                    zip_source = "indexed_vault"

        if zip_bytes is None:
            return AgentResult(
                answer=(
                    "I could not build a ZIP for that GitHub repo.\n\n"
                    "Try again with a public repo URL, or ingest the repo first so I can export your indexed snapshot."
                ),
                steps=steps,
                tools_used=tools,
                active_agent=self.name,
            )

        repo_name = _repo_slug_from_url(repo_url).replace("/", "_")
        suffix = "indexed_snapshot" if zip_source == "indexed_vault" else "github_snapshot"
        zip_name = f"{repo_name}_{suffix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        steps.append({"type": "tool_result", "tool": "export_repo_zip", "content": f"Built {zip_source} archive ({len(zip_bytes)} bytes)."})

        if zip_source == "indexed_vault":
            answer = (
                f"Created a downloadable ZIP from the indexed vault snapshot for {repo_url}. "
                f"Included {indexed_count} indexed snippet(s) from your latest local vault state."
            )
        else:
            answer = f"Created a downloadable ZIP from GitHub for {repo_url}."

        return AgentResult(
            answer=answer,
            steps=steps,
            tools_used=tools,
            active_agent=self.name,
            artifacts={
                "zip_bytes": zip_bytes,
                "zip_name": zip_name,
                "zip_source": zip_source,
            },
        )


class GeneralChatAgent(BaseVaultAgent):
    name = "GeneralChatAgent"
    description = "Answers non-vault general questions directly."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps = [{"type": "direct", "content": "No vault tool required."}]
        try:
            history = chat_history[-6:] if chat_history else []
            answer = _call_llm(
                backend,
                [
                    {"role": "system", "content": "You are a helpful assistant inside AI Code Vault. Be concise and practical."},
                    *history,
                    {"role": "user", "content": user_message},
                ],
                model=FAST_MODEL,
                temperature=0.4,
                max_tokens=900,
            )
        except Exception:
            answer = "Hi — I can help answer questions, search the vault with RAG, propose edits, review code, and generate tests."
        return AgentResult(answer=answer, steps=steps, tools_used=[], active_agent=self.name)


class SupervisorAgent(BaseVaultAgent):
    name = "SupervisorAgent"
    description = "Routes requests to the best specialist agent."

    def __init__(self) -> None:
        self.agents: Dict[str, BaseVaultAgent] = {
            "rag": RAGAnswerAgent(),
            "edit": PatchDiffGenerator(),
            "review": CodeReviewerAgent(),
            "test": TestStrategistAgent(),
            "docs": DocumentationAgent(),
            "zip": ZipExportAgent(),
            "quiz": QuizAgent(),
            "extract": ExtractAgent(),
            "analyze": AnalysisAgent(),
            "general": GeneralChatAgent(),
        }

    def route(self, user_message: str, chat_history: List[dict], backend: dict) -> Tuple[str, str]:
        text = user_message.lower()

        # Deterministic routing based on exact priority order requested in Section 3
        # CodeReviewerAgent: handles review, security, vulnerability, bug, improve, recommend, what's wrong (line-level)
        # AnalysisAgent: handles analyze, best practice (architectural analysis)
        if any(k in text for k in ["patch", "edit", "fix", "modify", "refactor"]):
            return "edit", "Matched editing intent."
        if any(k in text for k in ["test", "pytest", "unit test", "edge case"]):
            return "test", "Matched testing intent."
        if any(k in text for k in ["review", "security", "vulnerability", "bug", "improve", "recommend", "what's wrong"]):
            return "review", "Matched line-level review/security intent."
        if any(k in text for k in ["document", "docs", "readme"]):
            return "docs", "Matched documentation intent."
        if "summarize" in text:
            return "docs", "Matched summarize intent."
        if any(k in text for k in ["quiz", "test me", "questions about", "quiz me", "give me a quiz", "challenge me"]):
            return "quiz", "Matched quiz generation intent."
        if any(k in text for k in ["extract", "key points", "table of", "list all", "show all functions", "show all classes"]):
            return "extract", "Matched extraction intent."
        if any(k in text for k in ["analyze", "architectural", "best practice", "design pattern", "anti-pattern", "system design"]):
            return "analyze", "Matched architectural analysis intent."
        if any(k in text for k in ["zip", "export", "archive", "backup"]):
            return "zip", "Matched export intent."
        if len(text.split()) <= 3 and any(k in text for k in ["hi", "hello", "thanks"]):
            return "general", "Matched general chat intent."

        # Optional LLM router for ambiguous requests.
        try:
            raw = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "Route the user to exactly one agent: rag, edit, review, test, docs, zip, quiz, extract, analyze, general.\n"
                            "Descriptions:\n"
                            "- rag: general vault questions\n"
                            "- edit: proposes code patches\n"
                            "- review: line-level security/bugs\n"
                            "- test: generates unit tests\n"
                            "- docs: summaries and documentation\n"
                            "- zip: exports codebase as zip\n"
                            "- quiz: generates quiz questions from vault content\n"
                            "- extract: extracts tables or key points from vault content\n"
                            "- analyze: architectural analysis and design pattern identification\n"
                            "- general: greetings and non-code chat\n"
                            "Return JSON: {\"agent\": \"...\", \"reason\": \"...\"}."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
                model=FAST_MODEL,
                temperature=0,
                max_tokens=150,
            )
            parsed = _safe_json_loads(raw, {})
            agent = parsed.get("agent", "rag")
            if agent in self.agents:
                return agent, parsed.get("reason", "LLM router selected specialist.")
        except Exception:
            pass
        return "rag", "Defaulted to RAG for ambiguous request."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps = [{"type": "supervisor", "content": "Supervisor started routing."}]
        
        # Immediate disambiguation check to ask for the path if multiple matches exist
        get_engine = backend.get("get_engine")
        user_id = backend.get("current_user_id")
        if get_engine and user_id is not None:
            try:
                with Session(get_engine()) as session:
                    import db_connector
                    results = db_connector.run_hybrid_search(session, user_message, user_id, top_k=1)
                    if results and results[0].get("name") == "disambiguation_required":
                        return AgentResult(
                            answer=results[0]["snippet"],
                            steps=[{"type": "disambiguation", "content": "Multiple matches found; requesting path clarification."}],
                            tools_used=["search_vault"],
                            active_agent=self.name,
                        )
            except Exception:
                pass
                
        route_key, reason = self.route(user_message, chat_history, backend)
        steps.append({"type": "supervisor", "content": f"Routed to {self.agents[route_key].name}: {reason}"})
        result = self.agents[route_key].run(user_message, chat_history, backend)
        result.steps = steps + result.steps
        # Keep active_agent as the specialist name, not the supervisor.
        return result


# ---------------------------------------------------------------------------
# Public entry point used by streamlit_app.py
# ---------------------------------------------------------------------------

def run_agent(user_message: str, chat_history: list, backend: dict) -> dict:
    """Run one multi-agent turn and return a UI-friendly dict."""
    if not isinstance(chat_history, list):
        chat_history = []
    if chat_history and chat_history[-1].get("role") == "user" and chat_history[-1].get("content") == user_message:
        chat_history = chat_history[:-1]

    supervisor = SupervisorAgent()
    try:
        return supervisor.run(user_message, chat_history, backend).to_dict()
    except Exception as exc:
        err_text = str(exc)
        return AgentResult(
            answer=_build_provider_fallback(user_message, err_text),
            steps=[{"type": "error", "content": err_text}],
            tools_used=[],
            active_agent="SupervisorAgent",
        ).to_dict()


# ---------------------------------------------------------------------------
# Ingestion agent (ReAct-style minimal orchestrator)
# ---------------------------------------------------------------------------
def _update_scanjob(job_uuid: str, progress: int = None, status: str = None, finished: bool = False):
    try:
        if not job_uuid:
            return
        with Session(get_engine()) as s:
            job = s.query(ScanJob).filter(ScanJob.job_uuid == job_uuid).first()
            if not job:
                return
            if progress is not None:
                job.progress = int(progress)
            if status is not None:
                job.status = status
            if finished:
                job.finished_at = datetime.now()
            s.commit()
    except Exception:
        _log_debug("AGENT: failed to update ScanJob")


def run_ingest_agent(repo_url: str, user_id: int, job_uuid: str = None, max_chunks: int = None) -> dict:
    """Run a deterministic ingest pipeline as an agentic task.

    This function coordinates scanning, parsing, embedding, and storing with
    job progress updates. It is a synchronous, single-pass agent useful for
    turning a RAG pipeline into a tool-driven flow.
    """
    try:
        _log_debug(f"INGEST_AGENT: starting ingest for {repo_url} (user {user_id})")
        _update_scanjob(job_uuid, progress=1, status='Agent: scanning')
        chunks = get_repo_chunks(repo_url)
        total = len(chunks)
        if total == 0:
            _update_scanjob(job_uuid, progress=0, status='Agent: no chunks', finished=True)
            return {'status': 'no_chunks', 'total_chunks': 0}

        # Optionally limit
        if max_chunks:
            chunks = chunks[:max_chunks]
            total = len(chunks)

        _update_scanjob(job_uuid, progress=10, status='Agent: parsing')
        parsed = [parse_code_chunk(c) for c in chunks]

        _update_scanjob(job_uuid, progress=45, status='Agent: embedding')
        embeddings = get_embeddings([p['hub'].get('code_snippet', '') for p in parsed])

        _update_scanjob(job_uuid, progress=70, status='Agent: storing')
        stored = 0
        with Session(get_engine()) as s:
            for p, emb in zip(parsed, embeddings):
                hub = p.get('hub', {})
                key = hub.get('hash_key') or hub.get('file_path') or 'unknown'
                existing = s.query(Hub).filter(Hub.hash_key == key, Hub.user_id == user_id).first()
                if existing:
                    existing.code_snippet = hub.get('code_snippet', existing.code_snippet)
                    existing.embedding_vector = emb
                    existing.repo_url = repo_url
                    s.merge(existing)
                else:
                    new = Hub(
                        hash_key=key,
                        code_snippet=hub.get('code_snippet', ''),
                        embedding_vector=emb,
                        user_id=user_id,
                        repo_url=repo_url,
                    )
                    s.add(new)
                stored += 1
            s.commit()

        _update_scanjob(job_uuid, progress=100, status=f'Agent: complete — {stored} hubs', finished=True)
        _log_debug(f"INGEST_AGENT: complete for {repo_url} — stored {stored}")
        return {'status': 'complete', 'stored': stored, 'total': total}
    except Exception as e:
        _log_debug(f"INGEST_AGENT error: {e}")
        _log_debug(traceback.format_exc())
        _update_scanjob(job_uuid, progress=0, status=f'Agent: failure {e}', finished=True)
        return {'status': 'error', 'error': str(e)}
