# indexer.py
import sqlite3
import time
import os
from llm_client import LLMClient
from vectorstore import VectorStore
from utils import read_text_file, sha256_of_text, chunk_text, is_text_file
from helpers.extract_pdf import extract_pdf_text
from helpers.extract_docx import extract_docx_text
from dotenv import load_dotenv

load_dotenv()
EVENT_DB = os.environ.get('EVENT_DB', 'events.db')
client = LLMClient()
vs = VectorStore()

def extract_text_for_path(path: str) -> str:
    text = ''
    try:
        if is_text_file(path):
            text = read_text_file(path)
    except Exception:
        text = ''
    if text:
        return text
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        return extract_pdf_text(path)
    if ext in ('.docx',):
        return extract_docx_text(path)
    return ''

def process_row(row):
    _id, etype, path, ts = row
    if not os.path.exists(path):
        print('path missing', path)
        return
    text = extract_text_for_path(path)
    if not text:
        print('no extractable text', path)
        return
    sha = sha256_of_text(text)
    summary = text[:800] + ('...' if len(text) > 800 else '')
    chunks = chunk_text(text, chunk_size=1200, overlap=200)
    embeddings = client.embed(chunks)
    import numpy as np
    file_vec = np.mean(np.vstack(embeddings), axis=0)
    vs.upsert(path=path, summary=summary, vector=file_vec, timestamp=ts, sha256=sha)
    print('indexed', path)

def run_loop():
    conn = sqlite3.connect(EVENT_DB, check_same_thread=False)
    c = conn.cursor()
    while True:
        rows = c.execute('SELECT id, event_type, path, timestamp FROM events WHERE processed=0 ORDER BY id LIMIT 10').fetchall()
        if not rows:
            time.sleep(1)
            continue
        for r in rows:
            rid = r[0]
            try:
                process_row(r)
            except Exception as e:
                print('process error', e)
            c.execute('UPDATE events SET processed=1 WHERE id=?', (rid,))
        conn.commit()

if __name__ == '__main__':
    run_loop()
