# ============================================================================
# FILE PROCESSOR - File Upload & Text Extraction
# ============================================================================

import os
import re
from typing import List, Dict, Any
from pathlib import Path

def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from various file types.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Extracted text content
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == '.txt':
            return extract_text_plain(file_path)
        elif ext == '.pdf':
            return extract_text_pdf(file_path)
        elif ext == '.docx':
            return extract_text_docx(file_path)
        elif ext in ['.py', '.js', '.java', '.cpp', '.c', '.go', '.rb', '.php']:
            return extract_text_code(file_path)
        else:
            return extract_text_plain(file_path)
    except Exception as e:
        print(f"Error extracting text from {file_path}: {str(e)}")
        return ""

def extract_text_plain(file_path: str) -> str:
    """Extract text from plain text file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading plain text: {str(e)}")
        return ""

def extract_text_code(file_path: str) -> str:
    """Extract text from code file."""
    return extract_text_plain(file_path)

def extract_text_pdf(file_path: str) -> str:
    """Extract text from PDF file."""
    try:
        import PyPDF2
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text
    except ImportError:
        print("PyPDF2 not installed. Install with: pip install PyPDF2")
        return ""
    except Exception as e:
        print(f"Error extracting PDF: {str(e)}")
        return ""

def extract_text_docx(file_path: str) -> str:
    """Extract text from DOCX file."""
    try:
        from docx import Document
        doc = Document(file_path)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    except ImportError:
        print("python-docx not installed. Install with: pip install python-docx")
        return ""
    except Exception as e:
        print(f"Error extracting DOCX: {str(e)}")
        return ""

def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks for processing.
    
    Args:
        text: Text to chunk
        chunk_size: Size of each chunk in characters
        overlap: Overlap between chunks
        
    Returns:
        List of text chunks
    """
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
            # Add overlap from previous chunk
            if len(chunks) > 0:
                current_chunk = chunks[-1][-overlap:] + " " + sentence + " "
            else:
                current_chunk = sentence + " "
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

def validate_file(file_path: str, max_size_mb: int = 50) -> Dict[str, Any]:
    """
    Validate uploaded file.
    
    Args:
        file_path: Path to the file
        max_size_mb: Maximum file size in MB
        
    Returns:
        Validation result
    """
    if not os.path.exists(file_path):
        return {
            'valid': False,
            'error': 'File does not exist'
        }
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    if file_size_mb > max_size_mb:
        return {
            'valid': False,
            'error': f'File size {file_size_mb:.2f}MB exceeds maximum {max_size_mb}MB'
        }
    
    # Check file extension
    supported_extensions = {'.txt', '.pdf', '.docx', '.py', '.js', '.java', '.cpp', '.c', '.go', '.rb', '.php'}
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext not in supported_extensions:
        return {
            'valid': False,
            'error': f'File type {ext} not supported'
        }
    
    return {
        'valid': True,
        'size_mb': file_size_mb,
        'extension': ext
    }

def get_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract metadata from file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File metadata
    """
    stat = os.stat(file_path)
    
    return {
        'filename': os.path.basename(file_path),
        'size': stat.st_size,
        'created_at': stat.st_ctime,
        'modified_at': stat.st_mtime,
        'extension': os.path.splitext(file_path)[1].lower()
    }
