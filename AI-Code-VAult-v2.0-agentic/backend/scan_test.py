import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.repo_scanner import get_repo_chunks


if __name__ == '__main__':
    url = 'https://github.com/LibaMak/practice'
    print('Scanning', url)
    chunks = get_repo_chunks(url, max_chunk_size=1000)
    print('Chunks found:', len(chunks))
    for c in chunks[:10]:
        print('-', c.get('name'), c.get('type'), c.get('file_path'))
