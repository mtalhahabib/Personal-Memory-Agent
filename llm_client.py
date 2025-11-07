# llm_client.py
"""
LLM client adapted for Gemini CLI v0.12.0.

Behavior:
- Uses Gemini CLI for chat via the positional prompt and --output-format json when possible.
- Detects whether `gemini embeddings` is available; if not, falls back to deterministic stub vectors.
- Falls back to Ollama if LLM_BACKEND env is set or if gemini is not present.
- Keeps stub mode so the rest of the pipeline remains runnable for testing.

Set environment variable LLM_BACKEND=ollama to force ollama (or 'stub' to force stub).
"""

import os
import shutil
import subprocess
import tempfile
import json
import numpy as np
from typing import List, Optional

GEMINI_CMD = shutil.which('gemini') or shutil.which('gemini-cli')
OLLAMA_CMD = shutil.which('ollama')

VECTOR_DIM = 1536  # fallback deterministic vector dim

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

        # If using gemini, check whether the embeddings subcommand exists
        self._gemini_has_embeddings = False
        if self.backend == 'gemini' and GEMINI_CMD:
            self._gemini_has_embeddings = self._check_gemini_embeddings_available()

        print(f"[LLMClient] backend={self.backend}, gemini_has_embeddings={self._gemini_has_embeddings}")

    # ----------------
    # Public methods
    # ----------------
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        """
        Return list of numpy arrays (dtype=float32).
        If embeddings are not available for the selected backend, fall back to deterministic stub vectors.
        """
        if self.backend == 'gemini':
            if self._gemini_has_embeddings:
                return self._embed_gemini(texts)
            else:
                print("[LLMClient] gemini CLI does not expose an 'embeddings' subcommand on this install — returning stub vectors. "
                      "If you want real embeddings, install/enable gemini embeddings or set LLM_BACKEND=ollama and provide an embedding endpoint.")
                return [self._stub_vector(t) for t in texts]

        if self.backend == 'ollama':
            # Ollama CLI historically may not provide an embeddings subcommand; fallback to stub here.
            # You can modify this method to call an embedding server or the Ollama SDK if available.
            print("[LLMClient] ollama selected for embeddings: currently returning stub vectors (extend this method to call a real embedding API).")
            return [self._stub_vector(t) for t in texts]

        # stub
        return [self._stub_vector(t) for t in texts]

    def generate(self, system_prompt: str, user_prompt: str, context: str = '', max_tokens: int = 512) -> str:
        """
        Return string reply from the LLM. Uses Gemini (positional prompt) or Ollama if selected,
        otherwise returns a helpful stub reply.
        """
        if self.backend == 'gemini':
            return self._chat_gemini(system_prompt, user_prompt, context, max_tokens)
        if self.backend == 'ollama':
            return self._chat_ollama(system_prompt, user_prompt, context, max_tokens)
        # stub
        return f"[stub reply] Based on context, I would answer: {user_prompt}"

    # ----------------
    # Gemini: helper utils
    # ----------------
    def _check_gemini_embeddings_available(self) -> bool:
        """
        Heuristically check whether `gemini embeddings` exists on this gemini installation.
        Returns True if the command returns successfully for --help, False otherwise.
        """
        try:
            proc = subprocess.run([GEMINI_CMD, 'embeddings', '--help'], capture_output=True, text=True, check=False, timeout=3)
            # exit code 0 or nonzero but with output still suggests the subcommand exists; treat any output as presence
            has_output = bool((proc.stdout or proc.stderr))
            return has_output
        except Exception:
            return False

    # ----------------
    # Gemini embedding implementation (if available)
    # ----------------
    def _embed_gemini(self, texts: List[str]) -> List[np.ndarray]:
        vectors = []
        for t in texts:
            # write to temp file because some gemini CLI usage expects file input for embeddings
            with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as tf:
                tf.write(t)
                tf.flush()
                fname = tf.name
            # try a few variants historically seen in Gemini CLI ecosystems
            tried = False
            try_cmds = [
                [GEMINI_CMD, 'embeddings', fname],                     # candidate
                [GEMINI_CMD, 'embed', fname],                          # older/alternate
                [GEMINI_CMD, 'embeddings', '--file', fname],           # alternate flag form
            ]
            vec = None
            for cmd in try_cmds:
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
                    out = (proc.stdout or proc.stderr or '').strip()
                    if out:
                        # attempt to parse JSON first
                        try:
                            parsed = json.loads(out)
                            # common patterns: parsed could be {"embedding":[...]} or a raw list
                            if isinstance(parsed, dict) and 'embedding' in parsed:
                                arr = np.array(parsed['embedding'], dtype='float32')
                            elif isinstance(parsed, list):
                                arr = np.array(parsed, dtype='float32')
                            else:
                                # try to find floats inside structure
                                arr = self._floats_from_text(out)
                            vec = arr
                            tried = True
                            break
                        except Exception:
                            # fallback: parse floats from text output
                            arr = self._floats_from_text(out)
                            if arr is not None and arr.size > 0:
                                vec = arr
                                tried = True
                                break
                except subprocess.CalledProcessError as cpe:
                    # try next candidate command
                    continue
                except Exception:
                    continue
            if vec is None:
                print("[LLMClient] gemini embeddings: could not parse output, falling back to stub vector for this chunk.")
                vec = self._stub_vector(t)
            vectors.append(vec.astype('float32'))
            try:
                os.unlink(fname)
            except Exception:
                pass
        return vectors

    # ----------------
    # Gemini chat (positional prompt) implementation
    # ----------------
    def _chat_gemini(self, system_prompt: str, user_prompt: str, context: str = '', max_tokens: int = 512) -> str:
        # Compose prompt; don't use deprecated --prompt flag. Use positional prompt argument.
        prompt = f"{system_prompt}\n\nCONTEXT:\n{context}\n\nUSER:\n{user_prompt}"
        # Use JSON output format if available so we can parse structured response
        cmd = [GEMINI_CMD, '-o', 'json', prompt]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            out = (proc.stdout or proc.stderr or '').strip()
            # Try to parse JSON safely
            try:
                parsed = json.loads(out)
                # Geminis' JSON schema changes between versions. Try common fields:
                # - If parsed is dict and contains 'output' or 'content' or 'response', try to extract textual content.
                if isinstance(parsed, dict):
                    # heuristics across different gemini cli outputs
                    for key in ('output', 'response', 'content', 'result', 'choices'):
                        if key in parsed:
                            val = parsed[key]
                            # choices could be list of objects
                            if isinstance(val, list) and val:
                                # flatten strings in choices
                                if isinstance(val[0], dict) and 'text' in val[0]:
                                    return val[0].get('text') or json.dumps(val)
                                # if it's list of strings
                                if isinstance(val[0], str):
                                    return '\n'.join(val)
                            if isinstance(val, str):
                                return val
                            # fallback to json dump
                            return json.dumps(val)
                # If parsed is a list or other, try to flatten any strings
                if isinstance(parsed, list):
                    flat = []
                    for item in parsed:
                        if isinstance(item, str):
                            flat.append(item)
                        elif isinstance(item, dict):
                            # try common nested text keys
                            text = item.get('text') or item.get('content') or item.get('message') or None
                            if text:
                                flat.append(text)
                    if flat:
                        return '\n'.join(flat)
                # final fallback: return raw output
                return out
            except Exception:
                # not JSON — return raw text
                return out
        except subprocess.CalledProcessError as e:
            # gemini returned non-zero exit but maybe printed something
            out = (e.stdout or e.stderr or '').strip()
            return out or f"[gemini chat error: {e}]"
        except Exception as e:
            return f"[gemini chat invocation error: {e}]"

    # ----------------
    # Ollama chat fallback
    # ----------------
    def _chat_ollama(self, system_prompt: str, user_prompt: str, context: str = '', max_tokens: int = 512) -> str:
        prompt = f"{system_prompt}\n\nCONTEXT:\n{context}\n\nUSER:\n{user_prompt}"
        if not OLLAMA_CMD:
            return "[ollama not installed]"
        # Example: ollama run <model> "<prompt>" --once
        # Here we call a default model name; adjust as needed.
        cmd = [OLLAMA_CMD, 'run', 'llama2', prompt]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            return (proc.stdout or proc.stderr or '').strip()
        except subprocess.CalledProcessError as e:
            return (e.stdout or e.stderr or '').strip() or f"[ollama error: {e}]"
        except Exception as e:
            return f"[ollama invocation error: {e}]"

    # ----------------
    # Ollama embedding fallback placeholder (returns stub)
    # ----------------
    def _embed_ollama(self, texts: List[str]) -> List[np.ndarray]:
        print("[LLMClient] Ollama embedding not implemented in CLI wrapper — returning stub vectors.")
        return [self._stub_vector(t) for t in texts]

    # ----------------
    # Utility helpers
    # ----------------
    def _stub_vector(self, text: str) -> np.ndarray:
        """Deterministic pseudo-vector from SHA256 — useful for testing pipeline."""
        import hashlib
        h = hashlib.sha256(text.encode('utf-8')).digest()
        arr = np.frombuffer(h, dtype='uint8').astype('float32')
        if arr.size < VECTOR_DIM:
            arr = np.pad(arr, (0, VECTOR_DIM - arr.size), mode='wrap')
        return arr[:VECTOR_DIM]

    def _floats_from_text(self, out: str) -> np.ndarray:
        """Extract floats from an output string and return as numpy array (float32)."""
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

# end of llm_client.py
