import os
import json
import ast
from embeddings import get_embedding as generate_embedding
import numpy as np
from groq import Groq
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

# GROQ Configuration (client optional)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[GROQ] Client initialization failed: {e}. Continuing with local fallback.")
        client = None
else:
    print("[GROQ] Warning: GROQ_API_KEY not set; using local fallback parser only.")

"""Embedding provider is delegated to `backend/embeddings.py`.
`generate_embedding` is imported above as an alias for `get_embedding`.
"""


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


def parse_python_code(code_text: str, file_path: str, chunk_id: int = None) -> Dict[str, Any]:
    """Parse Python code using AST to extract deterministic metadata."""
    file_key = file_path if file_path else 'python_chunk'
    try:
        tree = ast.parse(code_text)
    except Exception:
        # parsing failure — return generic chunk
        logical_name = os.path.basename(file_path) if file_path else 'python_chunk'
        if chunk_id is not None:
            hash_key = f"{file_key}::{logical_name}::chunk_{chunk_id}"
        else:
            hash_key = f"{file_key}::{logical_name}"
        return {
            'hub': {
                'hash_key': hash_key,
                'type': 'module',
                'code_snippet': code_text,
                'file_path': file_path,
                'embedding': generate_embedding(code_text)
            },
            'links': [],
            'satellite': {
                'metrics': {
                    'lines_of_code': len(code_text.splitlines()),
                    'parameters': [],
                    'complexity_estimate': 'Medium'
                }
            }
        }

    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]

    # Determine primary hub
    if len(funcs) == 1 and not classes:
        primary = funcs[0]
        hub_type = 'function'
        logical_name = primary.name
        params = [a.arg for a in primary.args.args]
    elif len(classes) == 1 and not funcs:
        primary = classes[0]
        hub_type = 'class'
        logical_name = primary.name
        params = []
    else:
        hub_type = 'module'
        logical_name = os.path.basename(file_path) if file_path else 'module'
        params = []

    if chunk_id is not None:
        hash_key = f"{file_key}::{logical_name}::chunk_{chunk_id}"
    else:
        hash_key = f"{file_key}::{logical_name}"

    # Find simple call references (function names) as links
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append({'target_hash': node.func.id, 'relationship_type': 'calls'})
            elif isinstance(node.func, ast.Attribute):
                calls.append({'target_hash': node.func.attr, 'relationship_type': 'calls'})

    complexity = _estimate_complexity_from_ast(tree)

    return {
        'hub': {
            'hash_key': hash_key,
            'type': hub_type,
            'code_snippet': code_text,
            'file_path': file_path,
            'embedding': generate_embedding(code_text)
        },
        'links': calls,
        'satellite': {
            'metrics': {
                'lines_of_code': len(code_text.splitlines()),
                'parameters': params,
                'complexity_estimate': complexity
            }
        }
    }


def fallback_parse(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback parser when GROQ is not available or parsing fails."""
    code_text = chunk.get('code', '')
    embedding = generate_embedding(code_text)
    
    file_path = chunk.get('file_path', 'unknown')
    logical_name = chunk.get('name', 'unknown_entity')
    chunk_id = chunk.get('chunk_id')
    
    if chunk_id is not None:
        hash_key = f"{file_path}::{logical_name}::chunk_{chunk_id}"
    else:
        hash_key = f"{file_path}::{logical_name}"

    return {
        'hub': {
            'hash_key': hash_key,
            'type': chunk.get('type', 'chunk'),
            'code_snippet': code_text,
            'file_path': file_path,
            'embedding': embedding
        },
        'links': [],
        'satellite': {
            'metrics': {
                'lines_of_code': len(code_text.splitlines()),
                'parameters': [],
                'complexity_estimate': 'Medium'
            }
        }
    }


def parse_code_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a code chunk.

    Behavior:
    - For Python files, use a fast local AST-based parser (deterministic, zero-cost).
    - For other files, prefer the GROQ client when available; otherwise fallback.
    """
    code_text = chunk.get('code')
    if not code_text or not code_text.strip():
        return fallback_parse(chunk)

    file_path = chunk.get('file_path', '')
    file_ext = file_path.split('.')[-1].lower() if '.' in file_path else 'text'
    chunk_id = chunk.get('chunk_id')

    # Fast path: local deterministic parsing for Python
    if file_ext == 'py' or file_ext == 'python' or chunk.get('type') == '.py':
        try:
            return parse_python_code(code_text, file_path, chunk_id=chunk_id)
        except Exception as e:
            print(f"[PARSER] AST parse error: {e}. Falling back.")
            return fallback_parse(chunk)

    # Non-Python: prefer GROQ if configured
    if client is None:
        return fallback_parse(chunk)

    # Attempt GROQ parsing for non-Python file types
    try:
        SYSTEM_PROMPT = """
You are AI Knowledge Vault Parser. You receive chunks of code or technical documentation and must output a JSON object describing it.
Output ONLY valid JSON with keys: hub, links, satellite.
"""

        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': f'File Extension: {file_ext}\nContent:\n```{file_ext}\n{code_text}\n```'}
            ],
            temperature=0.2,
            max_tokens=1000,
            timeout=15
        )

        result_text = response.choices[0].message.content
        if result_text.startswith('```'):
            result_text = result_text.strip('`').strip()
            if result_text.startswith('json'):
                result_text = result_text[4:].strip()

        parsed = json.loads(result_text)
        parsed['hub']['code_snippet'] = code_text
        parsed['hub']['file_path'] = file_path
        parsed['hub']['embedding'] = generate_embedding(code_text)
        
        # Prepend file_path and append chunk_id to LLM-generated hash_key to prevent overwriting and allow search lookup
        logical_name = parsed['hub'].get('hash_key', 'chunk')
        if chunk_id is not None:
            parsed['hub']['hash_key'] = f"{file_path}::{logical_name}::chunk_{chunk_id}"
        else:
            parsed['hub']['hash_key'] = f"{file_path}::{logical_name}"
            
        return parsed
    except Exception:
        return fallback_parse(chunk)