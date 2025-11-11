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
import numpy as np

load_dotenv()
EVENT_DB = os.environ.get("EVENT_DB", "events.db")

client = LLMClient()
vs = VectorStore()

SUPPORTED_EXTRACTORS = {
    ".txt": read_text_file,
    ".md": read_text_file,
    ".py": read_text_file,
    ".js": read_text_file,
    ".json": read_text_file,
    ".csv": read_text_file,
    ".html": read_text_file,
    ".pdf": extract_pdf_text,
    ".docx": extract_docx_text
}

def extract_text_for_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    extractor = SUPPORTED_EXTRACTORS.get(ext, read_text_file)
    return extractor(path)

def process_row(row):
    _id, etype, path, ts = row
    if not os.path.exists(path):
        return
    text = extract_text_for_path(path)
    if not text:
        return
    sha = sha256_of_text(text)
    summary = text[:800] + ("..." if len(text) > 800 else "")
    chunks = chunk_text(text, chunk_size=1200, overlap=200)
    embeddings = client.embed(chunks)
    file_vec = np.mean(np.vstack(embeddings), axis=0)
    vs.upsert(path=path, summary=summary, vector=file_vec, timestamp=ts, sha256=sha)

def run_loop():
    conn = sqlite3.connect(EVENT_DB, check_same_thread=False)
    c = conn.cursor()
    while True:
        rows = c.execute(
            "SELECT id, event_type, path, timestamp FROM events WHERE processed=0 ORDER BY id LIMIT 10"
        ).fetchall()
        if not rows:
            time.sleep(1)
            continue
        for r in rows:
            rid = r[0]
            try:
                process_row(r)
            except Exception as e:
                print("Indexer error:", e)
            c.execute("UPDATE events SET processed=1 WHERE id=?", (rid,))
        conn.commit()

def semantic_search_documents(query, top_k=3):
    """Return top-k semantic matches for a query."""
    query_emb = client.embed([query])[0]
    results = vs.search(query_emb, top_k=top_k)
    formatted = []
    for score, meta in results:
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(meta['timestamp']))
        formatted.append(f"[{ts_str}] {meta['summary']}\n(path: {meta['path']}, score: {score:.2f})")
    return formatted

if __name__ == "__main__":
    run_loop()
