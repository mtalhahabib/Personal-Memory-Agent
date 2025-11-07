# utils.py
import os
import hashlib
from pathlib import Path
import magic

def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def is_text_file(path: str) -> bool:
    try:
        m = magic.from_file(path, mime=True)
        return m and (m.startswith('text/') or 'xml' in m or 'json' in m)
    except Exception:
        # fallback by extension
        ext = os.path.splitext(path)[1].lower()
        return ext in ('.txt', '.md', '.py', '.js', '.json', '.csv', '.html')

def read_text_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ''
    try:
        return p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding='latin-1')
        except Exception:
            return ''
    except Exception:
        return ''

def chunk_text(text: str, chunk_size=1000, overlap=200):
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i:i+chunk_size])
        i += chunk_size - overlap
    return chunks

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
