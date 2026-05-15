# ============================================================================
# REPOSITORY SCANNER - Git Repository Analysis & Chunking
# ============================================================================

import os
import re
import json
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime


def _win_on_rm_error(func, path, exc_info):
    """Error handler for shutil.rmtree to handle Windows read-only files.

    Attempts to set write permission and retry removal.
    """
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception:
        pass


def check_repo_accessible(repo_input: str, timeout: int = 15) -> bool:
    """Quickly verify repository is accessible without cloning.

    - For GitHub URLs: use `git ls-remote` to check reachability.
    - For local paths: check os.path.exists.
    Returns True if accessible, False otherwise.
    """
    if _is_github_url(repo_input):
        try:
            result = subprocess.run(['git', 'ls-remote', repo_input], capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0
        except Exception:
            return False
    else:
        return os.path.exists(repo_input)

def _log_debug(message: str):
    """Log debug messages to both console and a temp log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    # Also write to a portable temp location
    try:
        tmp = tempfile.gettempdir()
        log_file = os.path.join(tmp, "vault_v6_debug.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")

def _is_github_url(repo_input: str) -> bool:
    """Check if input is a GitHub URL."""
    return repo_input.startswith('https://github.com') or repo_input.startswith('git@github.com')

def _clone_github_repo(repo_url: str, timeout: int = 60) -> str:
    """Clone a GitHub repository or download and extract its ZIP archive as a fallback.

    Returns the path to a local directory containing the repository contents.
    """
    import zipfile
    from urllib.request import urlopen

    _log_debug(f"Cloning GitHub repo: {repo_url}")
    temp_dir = tempfile.mkdtemp(prefix="vault_repo_")
    try:
        # Try shallow git clone first
        result = subprocess.run(
            ['git', 'clone', '--depth', '1', repo_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            _log_debug(f"Successfully cloned to {temp_dir}")
            return temp_dir
        _log_debug(f"Git clone failed: {result.stderr or result.stdout}")
    except subprocess.TimeoutExpired:
        _log_debug(f"Git clone timed out after {timeout} seconds")
    except Exception as e:
        _log_debug(f"git clone raised exception: {e}")

    # ZIP fallback using GitHub API (public repos)
    try:
        _log_debug("Attempting GitHub ZIP fallback download...")
        # Derive zipball URL for the repository
        parsed = repo_url.rstrip('/')
        if parsed.endswith('.git'):
            parsed = parsed[:-4]
        parts = parsed.split('/')
        if len(parts) < 5:
            # Expecting https://github.com/owner/repo
            slug = '/'.join(parts[-2:])
        else:
            slug = '/'.join(parts[-2:])
        zip_url = f"https://api.github.com/repos/{slug}/zipball"
        _log_debug(f"Downloading ZIP from {zip_url}")
        with urlopen(zip_url, timeout=60) as resp:
            data = resp.read()
        # Write zip to temp file and extract
        zf_path = os.path.join(tempfile.gettempdir(), f"vault_{os.getpid()}_{int(datetime.now().timestamp())}.zip")
        with open(zf_path, 'wb') as zf:
            zf.write(data)
        with zipfile.ZipFile(zf_path, 'r') as zf:
            zf.extractall(temp_dir)
        os.remove(zf_path)
        # Some zipballs contain a single top-level dir; return that if present
        entries = [p for p in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, p))]
        if len(entries) == 1:
            extracted_root = os.path.join(temp_dir, entries[0])
            _log_debug(f"ZIP extracted; using {extracted_root} as repo root")
            return extracted_root
        _log_debug(f"ZIP extracted to {temp_dir}")
        return temp_dir
    except Exception as e:
        try:
            shutil.rmtree(temp_dir, onerror=_win_on_rm_error)
        except Exception:
            pass
        raise Exception(f"Failed to obtain repo via git or ZIP: {e}")

def get_repo_chunks(repo_path: str, max_chunk_size: int = 2000) -> List[Dict[str, Any]]:
    """
    Scan a repository and create code chunks for indexing.
    
    Args:
        repo_path: Path to the repository (local path or GitHub URL)
        max_chunk_size: Maximum characters per chunk
        
    Returns:
        List of code chunks with metadata
    """
    chunks = []
    supported_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.go', '.rb', '.php', '.ipynb'}
    temp_clone_dir = None
    
    try:
        # Handle GitHub URLs: clone first, then scan
        if _is_github_url(repo_path):
            _log_debug(f"Detected GitHub URL: {repo_path}")
            temp_clone_dir = _clone_github_repo(repo_path)
            scan_path = temp_clone_dir
        else:
            # Local path: validate existence
            if not os.path.exists(repo_path):
                _log_debug(f"Local path does not exist: {repo_path}")
                return []
            scan_path = repo_path
        
        _log_debug(f"Scanning repository at: {scan_path}")
        
        # Walk and collect chunks
        for root, dirs, files in os.walk(scan_path):
            # Skip hidden directories and common exclusions
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.git']]
            
            for file in files:
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                
                if ext in supported_extensions:
                    try:
                        # Special handling for Jupyter notebooks
                        if ext == '.ipynb':
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    nb = json.load(f)
                                # Concatenate all code cells
                                cells = []
                                for cell in nb.get('cells', []):
                                    if cell.get('cell_type') == 'code':
                                        cells.append('\n'.join(cell.get('source', []) or []))
                                content = '\n\n'.join(cells)
                            except Exception as ie:
                                _log_debug(f"Failed to parse notebook {file_path}: {ie}")
                                continue
                        else:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                        
                        # Split into chunks
                        if len(content) > max_chunk_size:
                            chunk_lines = []
                            current_chunk = ""
                            for line in content.split('\n'):
                                if len(current_chunk) + len(line) > max_chunk_size:
                                    if current_chunk:
                                        chunk_lines.append(current_chunk)
                                    current_chunk = line
                                else:
                                    current_chunk += line + "\n"
                            if current_chunk:
                                chunk_lines.append(current_chunk)
                        else:
                            chunk_lines = [content]
                        
                        for idx, chunk in enumerate(chunk_lines):
                            chunks.append({
                                'name': file,
                                'path': file_path,
                                'type': ext,
                                'code': chunk[:max_chunk_size],
                                'snippet': chunk[:max_chunk_size],
                                'chunk_id': idx,
                                'language': ext_to_language(ext),
                                'file_path': file_path,
                                'repo_url': repo_path  # Add repo_url to metadata
                            })
                    except Exception as e:
                        _log_debug(f"Error reading {file_path}: {str(e)}")
                        continue
        
        _log_debug(f"Successfully scanned {len(chunks)} code chunks from {scan_path}")
        if len(chunks) == 0:
            _log_debug(f"Warning: No supported code files found under {scan_path}. Checked extensions: {sorted(list(supported_extensions))}")
    except Exception as e:
        _log_debug(f"Error scanning repository: {str(e)}")
    finally:
        # Clean up temporary clone directory
        if temp_clone_dir and os.path.exists(temp_clone_dir):
            try:
                shutil.rmtree(temp_clone_dir, onerror=_win_on_rm_error)
                _log_debug(f"Cleaned up temp directory: {temp_clone_dir}")
            except Exception as e:
                _log_debug(f"Warning: Failed to clean up temp directory {temp_clone_dir}: {e}")
    
    return chunks

def ext_to_language(ext: str) -> str:
    """Convert file extension to language name."""
    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.go': 'go',
        '.rb': 'ruby',
        '.php': 'php'
    }
    return ext_map.get(ext, 'text')

def analyze_code_metrics(code_snippet: str) -> Dict[str, Any]:
    """
    Analyze code snippet for complexity metrics.
    
    Args:
        code_snippet: Source code to analyze
        
    Returns:
        Dictionary with metrics
    """
    lines = code_snippet.split('\n')
    
    # Count metrics
    loc = len(lines)
    code_lines = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
    complexity = estimate_complexity(code_snippet)
    functions = len(re.findall(r'def |function |func ', code_snippet))
    classes = len(re.findall(r'class ', code_snippet))
    
    return {
        'lines_of_code': loc,
        'code_lines': code_lines,
        'complexity_estimate': complexity,
        'functions': functions,
        'classes': classes
    }

def estimate_complexity(code: str) -> str:
    """Estimate cyclomatic complexity (Low/Medium/High)."""
    # Simple heuristic based on control flow keywords
    keywords = ['if', 'else', 'for', 'while', 'try', 'except', 'switch', 'case']
    count = sum(len(re.findall(rf'\b{kw}\b', code)) for kw in keywords)
    
    if count < 5:
        return 'Low'
    elif count < 15:
        return 'Medium'
    else:
        return 'High'
