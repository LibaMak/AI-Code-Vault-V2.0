import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.repo_scanner import get_repo_chunks

if __name__ == '__main__':
    url = sys.argv[1] if len(sys.argv) > 1 else 'https://github.com/hassanali-codes/ai-legal-aid-pakistan'
    print('Scanning', url)
    chunks = get_repo_chunks(url, max_chunk_size=2000)
    print('Chunks found:', len(chunks))
    for i, c in enumerate(chunks[:20], start=1):
        print(f"{i}. {c.get('name')} ({c.get('type')}) - {c.get('file_path')}")
    if len(chunks) > 20:
        print('...and', len(chunks)-20, 'more chunks')
