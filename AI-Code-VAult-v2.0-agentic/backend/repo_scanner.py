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

def _log_debug(message: str):
    """Log debug messages to both console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    
    # Also write to log file
    try:
        log_file = "/tmp/vault_v6_debug.log"
        with open(log_file, "a") as f:
            f.write(log_message + "\n")
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")

def _is_github_url(repo_input: str) -> bool:
    """Check if input is a GitHub URL."""
    return repo_input.startswith('https://github.com') or repo_input.startswith('git@github.com')

def _clone_github_repo(repo_url: str, timeout: int = 60) -> str:
    """
    Clone a GitHub repository to a temporary directory.
    
    Args:
        repo_url: GitHub repository URL
        timeout: Clone timeout in seconds
        
    Returns:
        Path to the cloned repository
        
    Raises:
        Exception if clone fails
    """
    _log_debug(f"Cloning GitHub repo: {repo_url}")
    temp_dir = tempfile.mkdtemp(prefix="vault_repo_")
    try:
        # Use git clone with shallow clone for speed
        result = subprocess.run(
            ['git', 'clone', '--depth', '1', repo_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            _log_debug(f"Git clone failed: {error_msg}")
            raise Exception(f"Failed to clone repo: {error_msg}")
        
        _log_debug(f"Successfully cloned to {temp_dir}")
        return temp_dir
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise Exception(f"Repository clone timed out after {timeout} seconds")
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

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
    supported_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.go', '.rb', '.php'}
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
    except Exception as e:
        _log_debug(f"Error scanning repository: {str(e)}")
    finally:
        # Clean up temporary clone directory
        if temp_clone_dir and os.path.exists(temp_clone_dir):
            try:
                shutil.rmtree(temp_clone_dir)
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
