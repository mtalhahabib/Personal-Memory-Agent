# vectorstore.py
import sqlite3
import numpy as np
import os
from typing import List, Tuple

DB_PATH = os.environ.get("VECTOR_DB", "memory_vectors.db")

def to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype("float32").tobytes()

def from_bytes(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype="float32")

class VectorStore:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS vectors (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            summary TEXT,
            embedding BLOB,
            timestamp REAL,
            sha256 TEXT
        )
        """)
        self.conn.commit()

    def upsert(self, path: str, summary: str, vector: np.ndarray, timestamp: float, sha256: str):
        c = self.conn.cursor()
        c.execute("""
        INSERT OR REPLACE INTO vectors (path, summary, embedding, timestamp, sha256)
        VALUES (?, ?, ?, ?, ?)
        """, (path, summary, to_bytes(vector), timestamp, sha256))
        self.conn.commit()

    def all_embeddings(self) -> List[Tuple[int, str, str, np.ndarray, float]]:
        c = self.conn.cursor()
        rows = c.execute("SELECT id, path, summary, embedding, timestamp FROM vectors").fetchall()
        return [(rid, path, summary, from_bytes(emb), ts) for rid, path, summary, emb, ts in rows]

    def search(self, query_vector: np.ndarray, top_k=5):
        rows = self.all_embeddings()
        if not rows:
            return []
        ids, paths, summaries, vecs, ts = zip(*rows)
        mat = np.vstack(vecs)
        q = query_vector.astype("float32")
        q_norm = np.linalg.norm(q) or 1e-12
        mat_norms = np.linalg.norm(mat, axis=1)
        denom = mat_norms * q_norm
        scores = (mat @ q) / np.where(denom == 0, 1e-12, denom)
        idx = np.argsort(scores)[::-1][:top_k]
        return [(float(scores[i]), {"id": int(ids[i]), "path": paths[i], "summary": summaries[i], "timestamp": float(ts[i])}) for i in idx]
