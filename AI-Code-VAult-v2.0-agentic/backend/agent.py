# backend/agent.py
"""Multi-agent layer for AI Code Vault 2.0.

This module exposes ``run_agent(user_message, chat_history, backend)`` for the
Streamlit UI.  It implements a small agentic team:

- SupervisorAgent: routes the user request and coordinates other agents.
- RAGAnswerAgent: answers questions with retrieval-augmented generation.
- CodeEditorAgent: drafts/apply-safe edits to indexed vault snippets.
- CodeReviewerAgent: reviews code for quality, security, and performance.
- TestStrategistAgent: suggests tests and validation plans.
- DocumentationAgent: creates summaries, docs, and onboarding notes.

The editor intentionally edits the *indexed vault copy* only. It does not write
back to a remote GitHub repository. Returned patches can be copied into a real
repo, and an explicit "apply/save/update the vault" request can update the
matching Hub.code_snippet in the local database.
"""

from __future__ import annotations

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

# Load .env from project root so GROQ_API_KEY is available when running Streamlit.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

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
    try:
        results = search_fn(query, top_k=top_k)
    except TypeError:
        results = search_fn(query)
    except Exception as exc:
        return [{"name": "search_error", "snippet": str(exc), "score": 0}]

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
    for common requests so the CodeEditorAgent can still produce a useful diff
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
                answer="I could not find relevant indexed vault context. Ingest a repository/file first, or ask a more specific question.",
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
                            "If evidence is missing, say what is missing. Cite source names inline."
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

        if "source" not in answer.lower():
            answer += f"\n\nSources: {_source_list(results)}"
        return AgentResult(answer=answer, steps=steps, tools_used=tools, active_agent=self.name)


class CodeEditorAgent(BaseVaultAgent):
    name = "CodeEditorAgent"
    description = "Drafts diffs and can update indexed vault snippets on explicit request."

    def run(self, user_message: str, chat_history: List[dict], backend: dict) -> AgentResult:
        steps: List[dict] = []
        tools = ["search_vault", "generate_patch"]
        results = _run_search(backend, user_message, top_k=5)
        steps.append({"type": "tool_call", "tool": "search_vault", "content": f"Located {len(results)} candidate snippet(s) for editing."})
        if not results:
            return AgentResult(
                answer="I could not find an indexed file/snippet to edit. Ingest the target repo/file first or mention the exact hub/file name.",
                steps=steps,
                tools_used=tools,
                active_agent=self.name,
            )

        target = results[0]
        target_name = str(target.get("name", "unknown"))
        old_code = str(target.get("snippet", ""))
        context = _format_sources(results, max_chars=7000)

        try:
            raw = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a careful code editing agent. Return ONLY JSON with keys: "
                            "summary (string), edited_code (string), notes (array of strings). "
                            "Preserve existing behavior unless the user asks for a change."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Edit request:\n{user_message}\n\nBest target: {target_name}\n\n"
                            f"Relevant vault context:\n{context}\n\nReturn the full edited code for the best target."
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=1800,
            )
            parsed = _safe_json_loads(raw, {})
            summary = parsed.get("summary") if isinstance(parsed, dict) else None
            new_code = parsed.get("edited_code") if isinstance(parsed, dict) else None
            notes = parsed.get("notes", []) if isinstance(parsed, dict) else []
            if not new_code:
                raise ValueError("The model did not return edited_code JSON.")
        except Exception as exc:
            steps.append({"type": "fallback", "content": f"Patch generation fallback: {exc}"})
            heuristic = _heuristic_edit(user_message, old_code)
            if heuristic:
                summary, new_code, notes = heuristic
            else:
                summary = "Could not generate an automatic patch because the LLM is unavailable."
                new_code = old_code
                notes = [
                    "Configure GROQ_API_KEY or an active Admin KeyPool key, then retry.",
                    "If you just added a key in the UI, refresh the page so the active session picks it up.",
                ]

        diff = _build_unified_diff(target_name, old_code, new_code) if new_code != old_code else ""
        steps.append({"type": "tool_result", "tool": "generate_patch", "content": f"Generated diff with {len(diff)} characters."})

        apply_note = ""
        if _wants_apply(user_message) and diff:
            tools.append("update_indexed_snippet")
            ok, msg = _update_indexed_snippet(backend, target_name, new_code)
            steps.append({"type": "tool_result", "tool": "update_indexed_snippet", "content": msg})
            apply_note = f"\n\nVault update: {'✅' if ok else '⚠️'} {msg}"
        elif diff:
            apply_note = "\n\nI did not apply this automatically. Say **apply/save this edit** to update the indexed vault snippet."

        answer = f"### {self.name}: proposed edit for `{target_name}`\n\n{summary or 'Proposed code edit.'}\n"
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
            "edit": CodeEditorAgent(),
            "review": CodeReviewerAgent(),
            "test": TestStrategistAgent(),
            "docs": DocumentationAgent(),
            "zip": ZipExportAgent(),
            "general": GeneralChatAgent(),
        }

    def route(self, user_message: str, chat_history: List[dict], backend: dict) -> Tuple[str, str]:
        text = user_message.lower()

        # Deterministic fast route first.
        if any(k in text for k in ["zip", "archive", "downloadable", "backup", "export bundle"]):
            return "zip", "Matched archive/export intent."
        if any(k in text for k in ["edit", "change", "modify", "patch", "fix this", "refactor", "apply", "update the code"]):
            return "edit", "Matched editing/refactoring intent."
        if any(k in text for k in ["test", "pytest", "unit test", "integration test", "edge case"]):
            return "test", "Matched testing intent."
        if any(k in text for k in ["review", "security", "vulnerability", "performance", "bug", "best practice", "optimize"]):
            return "review", "Matched review/security/performance intent."
        if any(k in text for k in ["document", "docs", "readme", "summary", "summarize", "onboarding", "explain architecture"]):
            return "docs", "Matched documentation/summary intent."
        if any(k in text for k in ["vault", "repo", "repository", "code", "file", "function", "class", "where is", "how does"]):
            return "rag", "Matched vault/code question intent."
        if len(text.split()) <= 3 and any(k in text for k in ["hi", "hello", "hey", "thanks"]):
            return "general", "Matched general chat intent."

        # Optional LLM router for ambiguous requests.
        try:
            raw = _call_llm(
                backend,
                [
                    {
                        "role": "system",
                        "content": (
                            "Route the user to exactly one agent: rag, edit, review, test, docs, zip, general. "
                            "Return JSON: {\"agent\": \"...\", \"reason\": \"...\"}."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
                model=FAST_MODEL,
                temperature=0,
                max_tokens=120,
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
