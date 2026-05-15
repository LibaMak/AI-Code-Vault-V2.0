import os
import json
import numpy as np
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# GROQ Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PRIMARY_MODEL = "llama-3.3-70b-versatile"    # Heavy tasks - code analysis, parsing
FAST_MODEL = "llama-3.1-8b-instant"           # Light tasks - quick operations

# Initialize GROQ client lazily and fail-safe: do not raise on missing/invalid API key.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[GROQ] Client initialization failed: {e}. Continuing with local fallback.")
        client = None
else:
    print("[GROQ] Warning: GROQ_API_KEY not set; using local fallback parser only.")

SYSTEM_PROMPT = """
You are AI Knowledge Vault Parser. You receive chunks of code or technical documentation and must output a JSON object describing it.
Identify the core object as a 'hub', its outgoing calls/references as 'links', and metadata as 'satellites'.
Identify the 'type' of the hub as one of: 'function', 'class', 'component', 'module', 'document', or 'chunk'.

Output ONLY valid JSON matching this schema:
{
  "hub": {
    "hash_key": "string (name of function, class, or document section)",
    "type": "string (from the list above)"
  },
  "links": [
    { "target_hash": "string (name of entity being referenced)", "relationship_type": "calls or references" }
  ],
  "satellite": {
    "metrics": {
      "lines_of_code": integer,
      "parameters": ["list", "of", "args/props"],
      "complexity_estimate": "low/medium/high"
    }
  }
}
"""

def generate_embedding(text):
    """
    Generate deterministic mock vector embeddings using SHA256.
    No external API needed — fully local and free.
    """
    if not text:
        return np.zeros(1536).tolist()
    import hashlib as _hashlib

    hash_obj = _hashlib.sha256(text.encode('utf-8'))
    seed = int(hash_obj.hexdigest(), 16) % (2**32)
    np.random.seed(seed)
    vector = np.random.rand(1536).tolist()
    return vector

def fallback_parse(chunk):
    """
    Fallback parser if GROQ API fails.
    Ensures app always works even without API.
    """
    code_text = chunk.get("code", "")
    # Compute embedding robustly: prefer `generate_embedding`, but handle any NameError
    try:
        embedding = generate_embedding(code_text)
    except Exception as ee:
        print(f"[FALLBACK] generate_embedding failed: {ee}. Using inline fallback.")
        try:
            import hashlib as _hashlib
            if code_text:
                _hash = _hashlib.sha256(code_text.encode('utf-8'))
                seed = int(_hash.hexdigest(), 16) % (2**32)
                np.random.seed(seed)
                embedding = np.random.rand(1536).tolist()
            else:
                embedding = [0.0] * 1536
        except Exception as _e:
            print(f"[FALLBACK] inline embedding also failed: {_e}. Using zeros.")
            embedding = [0.0] * 1536

    return {
        "hub": {
            "hash_key": chunk.get("name", "unknown_entity"),
            "type": chunk.get("type", "chunk"),
            "code_snippet": code_text,
            "file_path": chunk.get("file_path", "unknown"),
            "embedding": embedding
        },
        "links": [],
        "satellite": {
            "metrics": {
                "lines_of_code": len(code_text.splitlines()),
                "parameters": [],
                "complexity_estimate": "medium"
            }
        }
    }

def parse_code_chunk(chunk):
    """
    Parse a code chunk using GROQ LLM.
    Falls back to fallback_parse() if API fails.
    """
    code_text = chunk.get("code")
    
    # Empty chunk check
    if not code_text or not code_text.strip():
        return fallback_parse(chunk)
    
    file_path = chunk.get("file_path", "")
    file_ext = file_path.split('.')[-1].lower() if '.' in file_path else 'text'
    print(f"[GROQ] Parsing {file_ext} chunk: {chunk.get('name')} from {file_path}")

    try:
        if client is None:
            raise RuntimeError("GROQ client not configured; falling back to local parser")

        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"File Extension: {file_ext}\nContent:\n```{file_ext}\n{code_text}\n```"}
            ],
            temperature=0.2,        # Low temp = precise, no hallucinations
            max_tokens=1000,
            timeout=15
        )

        result_text = response.choices[0].message.content

        # Strip markdown if GROQ wraps in ```json
        if result_text.startswith("```"):
            result_text = result_text.strip("`").strip()
            if result_text.startswith("json"):
                result_text = result_text[4:].strip()

        parsed = json.loads(result_text)

        # Inject standard fields
        parsed['hub']['code_snippet'] = code_text
        parsed['hub']['file_path'] = file_path
        parsed['hub']['embedding'] = generate_embedding(code_text)

        return parsed

    except json.JSONDecodeError:
        print(f"[GROQ] JSON parse error for {chunk.get('name')}. Using fallback.")
        return fallback_parse(chunk)
    except Exception as e:
        print(f"[GROQ] API error for {chunk.get('name')}. Using fallback.")
        return fallback_parse(chunk)