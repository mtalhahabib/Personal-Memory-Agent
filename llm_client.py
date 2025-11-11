# llm_client.py
"""
Professional LLM client for Gemini CLI, Ollama CLI, or Google Generative AI.
Supports embeddings and chat with fallback stubs.
"""
import os
import shutil
import subprocess
import tempfile
import json
import numpy as np
from typing import List, Optional

VECTOR_DIM = 3072
GEMINI_CMD = shutil.which('gemini') or shutil.which('gemini-cli')
OLLAMA_CMD = shutil.which('ollama')

try:
    from google import generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

class LLMClient:
    def __init__(self, backend_override: Optional[str] = None):
        self.backend = backend_override or os.environ.get('LLM_BACKEND') or self._detect_backend()
        self._genai_available = GENAI_AVAILABLE and bool(os.environ.get("GEMINI_API_KEY"))
        if self._genai_available:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

    def _detect_backend(self):
        if GEMINI_CMD:
            return "gemini"
        if OLLAMA_CMD:
            return "ollama"
        return "stub"

    # ----------------
    # Public methods
    # ----------------
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        if self.backend == "gemini":
            return self._embed_gemini(texts)
        if self.backend == "ollama":
            return [self._stub_vector(t) for t in texts]
        return [self._stub_vector(t) for t in texts]

    def generate(self, prompt: str, max_tokens=512) -> str:
        if self.backend == "gemini":
            return self._chat_gemini(prompt)
        if self.backend == "ollama":
            return self._chat_ollama(prompt)
        return self._stub_chat(prompt)

    # ----------------
    # Private helpers
    # ----------------
    def _embed_gemini(self, texts: List[str]) -> List[np.ndarray]:
        vectors = []
        for t in texts:
            vec = None
            if self._genai_available:
                try:
                    resp = genai.embed_content(model="gemini-embedding-001", content=t)
                    vec = np.array(resp["embedding"], dtype="float32")
                    if vec.size != VECTOR_DIM:
                        vec = np.pad(vec, (0, VECTOR_DIM - vec.size), mode='wrap')[:VECTOR_DIM]
                except Exception:
                    vec = self._stub_vector(t)
            else:
                vec = self._stub_vector(t)
            vectors.append(vec)
        return vectors

    def _chat_gemini(self, prompt: str) -> str:
        if not self._genai_available:
            return "[Gemini Error] API key not found."
        try:
            model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"))
            resp = model.generate_content(prompt)
            return resp.text.strip() if resp.text else "[Gemini returned empty response]"
        except Exception as e:
            return f"[Gemini Error] {e}"

    def _chat_ollama(self, prompt: str) -> str:
        if not OLLAMA_CMD:
            return "[Ollama Error] CLI not installed."
        try:
            result = subprocess.run(
                ["ollama", "run", os.environ.get("OLLAMA_MODEL", "llama3"), prompt],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.stdout.strip()
        except Exception as e:
            return f"[Ollama Error] {e}"

    def _stub_vector(self, text: str) -> np.ndarray:
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        arr = np.frombuffer(h, dtype="uint8").astype("float32")
        if arr.size < VECTOR_DIM:
            arr = np.pad(arr, (0, VECTOR_DIM - arr.size), mode='wrap')
        return arr[:VECTOR_DIM]

    def _stub_chat(self, prompt: str) -> str:
        return f"[stub] No LLM connected. You asked: {prompt}"
