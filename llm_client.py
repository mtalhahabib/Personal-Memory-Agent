# llm_client.py
"""
LLM client adapted for Gemini CLI v0.12.0.

Behavior:
- Uses Gemini CLI for chat via the positional prompt and --output-format json when possible.
- Detects whether `gemini embeddings` is available; if not, falls back to deterministic stub vectors.
- Keeps stub mode so the rest of the pipeline remains runnable for testing.

Set environment variable LLM_BACKEND=ollama to force ollama (or 'stub' to force stub).
"""

try:
    from google import generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

import os
import shutil
import subprocess
import tempfile
import json
import numpy as np
from typing import List, Optional

GEMINI_CMD = shutil.which('gemini') or shutil.which('gemini-cli')
OLLAMA_CMD = shutil.which('ollama')

VECTOR_DIM = 3072  # match Gemini embeddings dimension

class LLMClient:
    def __init__(self, backend_override: Optional[str] = None):
        env = os.environ.get('LLM_BACKEND')
        self.backend = backend_override or env or None

        if not self.backend:
            if GEMINI_CMD:
                self.backend = 'gemini'
            elif OLLAMA_CMD:
                self.backend = 'ollama'
            else:
                self.backend = 'stub'

        # Check if Gemini CLI has embeddings subcommand
        self._gemini_has_embeddings = False
        if self.backend == 'gemini' and GEMINI_CMD:
            self._gemini_has_embeddings = self._check_gemini_embeddings_available()

        self._genai_available = GENAI_AVAILABLE and os.environ.get("GEMINI_API_KEY")
        if self._genai_available:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

        print(f"[LLMClient] backend={self.backend}, gemini_has_embeddings={self._gemini_has_embeddings}")

    # ----------------
    # Public methods
    # ----------------
    def _embed_google(self, texts: List[str]) -> List[np.ndarray]:
        if not self._genai_available:
            print("[LLMClient] google-generativeai embeddings not available — using stub vectors.")
            return [self._stub_vector(t) for t in texts]

        vectors = []
        for t in texts:
            try:
                resp = genai.embed_content(
                    model="gemini-embedding-001",
                    content=t
                )
                vec = np.array(resp["embedding"], dtype="float32")
                # ensure consistent VECTOR_DIM
                if vec.size != VECTOR_DIM:
                    vec = vec[:VECTOR_DIM] if vec.size > VECTOR_DIM else np.pad(vec, (0, VECTOR_DIM - vec.size))
            except Exception as e:
                print(f"[LLMClient] Google embeddings error: {e}, using stub vector instead.")
                vec = self._stub_vector(t)
            vectors.append(vec)
        return vectors

    def embed(self, texts: List[str]) -> List[np.ndarray]:
        """
        Return list of numpy arrays (dtype=float32).
        """
        if self.backend == 'gemini':
            if self._gemini_has_embeddings:
                return self._embed_gemini(texts)
            else:
                print("[LLMClient] gemini CLI does not expose an 'embeddings' subcommand — using Google Generative AI embeddings instead.")
                return self._embed_google(texts)

        if self.backend == 'ollama':
            print("[LLMClient] ollama selected for embeddings: returning stub vectors.")
            return [self._stub_vector(t) for t in texts]

        # stub fallback
        return [self._stub_vector(t) for t in texts]

    def generate(self, system_prompt: str, user_prompt: str, context: str = '', max_tokens: int = 512) -> str:
        """
        Return string reply from the LLM.
        """
        if self.backend == 'gemini':
            return self._chat_gemini(system_prompt, user_prompt, context, max_tokens)
        if self.backend == 'ollama':
            return self._chat_ollama(system_prompt, user_prompt, context, max_tokens)
        return f"[stub reply] Based on context, I would answer: {user_prompt}"

    # ----------------
    # Gemini CLI helpers
    # ----------------
    def _check_gemini_embeddings_available(self) -> bool:
        try:
            proc = subprocess.run([GEMINI_CMD, 'embed', '--help'], capture_output=True, text=True, check=False, timeout=3)
            return bool(proc.stdout or proc.stderr)
        except Exception:
            return False

    def _embed_gemini(self, texts: List[str]) -> List[np.ndarray]:
        vectors = []
        for t in texts:
            with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as tf:
                tf.write(t)
                tf.flush()
                fname = tf.name

            vec = None
            try_cmds = [[GEMINI_CMD, 'embed', fname, '--output-format', 'json']]

            for cmd in try_cmds:
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
                    out = (proc.stdout or proc.stderr or '').strip()
                    if not out:
                        continue

                    try:
                        parsed = json.loads(out)
                        if isinstance(parsed, dict) and 'embedding' in parsed:
                            vec = np.array(parsed['embedding'], dtype='float32')
                        elif isinstance(parsed, list):
                            vec = np.array(parsed, dtype='float32')
                    except Exception:
                        vec = self._floats_from_text(out)

                    if vec is not None:
                        if vec.size != VECTOR_DIM:
                            vec = vec[:VECTOR_DIM] if vec.size > VECTOR_DIM else np.pad(vec, (0, VECTOR_DIM - vec.size))
                        break
                except Exception:
                    continue

            if vec is None:
                vec = self._stub_vector(t)
            vectors.append(vec.astype('float32'))
            try:
                os.unlink(fname)
            except Exception:
                pass
        return vectors

    def _chat_gemini(self, system_prompt: str, user_prompt: str, context: str = '', max_tokens: int = 512) -> str:
        prompt = f"{system_prompt}\n\nCONTEXT:\n{context}\n\nUSER:\n{user_prompt}"
        cmd = [GEMINI_CMD, '-o', 'json', prompt]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            out = (proc.stdout or proc.stderr or '').strip()
            try:
                parsed = json.loads(out)
                if isinstance(parsed, dict):
                    for key in ('output', 'response', 'content', 'result', 'choices'):
                        if key in parsed:
                            val = parsed[key]
                            if isinstance(val, list):
                                if isinstance(val[0], dict) and 'text' in val[0]:
                                    return val[0].get('text') or json.dumps(val)
                                if isinstance(val[0], str):
                                    return '\n'.join(val)
                            if isinstance(val, str):
                                return val
                    return json.dumps(parsed)
                if isinstance(parsed, list):
                    flat = [item.get('text') or item.get('content') for item in parsed if isinstance(item, dict)]
                    return '\n'.join(flat) if flat else str(parsed)
                return out
            except Exception:
                return out
        except Exception as e:
            return f"[gemini chat error: {e}]"

    # ----------------
    # Ollama fallback
    # ----------------
    def _chat_ollama(self, system_prompt: str, user_prompt: str, context: str = '', max_tokens: int = 512) -> str:
        prompt = f"{system_prompt}\n\nCONTEXT:\n{context}\n\nUSER:\n{user_prompt}"
        if not OLLAMA_CMD:
            return "[ollama not installed]"
        try:
            proc = subprocess.run([OLLAMA_CMD, 'run', 'llama2', prompt], capture_output=True, text=True, check=True, timeout=60)
            return (proc.stdout or proc.stderr or '').strip()
        except Exception as e:
            return f"[ollama error: {e}]"

    def _stub_vector(self, text: str) -> np.ndarray:
        """Deterministic pseudo-vector from SHA256."""
        import hashlib
        h = hashlib.sha256(text.encode('utf-8')).digest()
        arr = np.frombuffer(h, dtype='uint8').astype('float32')
        if arr.size < VECTOR_DIM:
            arr = np.pad(arr, (0, VECTOR_DIM - arr.size), mode='wrap')
        return arr[:VECTOR_DIM]

    def _floats_from_text(self, out: str) -> np.ndarray:
        parts = []
        for token in out.replace(',', ' ').split():
            try:
                parts.append(float(token))
            except Exception:
                continue
        if not parts:
            return np.zeros(VECTOR_DIM, dtype='float32')
        arr = np.array(parts, dtype='float32')
        if arr.size < VECTOR_DIM:
            arr = np.pad(arr, (0, VECTOR_DIM - arr.size), mode='wrap')
        elif arr.size > VECTOR_DIM:
            arr = arr[:VECTOR_DIM]
        return arr
