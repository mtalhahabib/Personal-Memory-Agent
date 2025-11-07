# --------------------------------------------------------------------
# 📄 Semantic Document Search Context
# --------------------------------------------------------------------
from vectorstore import VectorStore
from llm_client import LLMClient

def semantic_search_documents(query, top_k=3):
    vs = VectorStore()
    client = LLMClient()
    # Generate embedding for the query
    query_emb = client.embed([query])[0]
    results = vs.search(query_emb, top_k=top_k)
    formatted = []
    for score, meta in results:
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(meta['timestamp']))
        formatted.append(f"[{ts_str}] {meta['summary']}\n(path: {meta['path']}, score: {score:.2f})")
    return formatted
# --------------------------------------------------------------------
# 🌐 Browser History Context
# --------------------------------------------------------------------
def search_recent_browser_history(db_path, days=2):
    """Fetch browser history records from the last N days."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        now = int(time.time())
        since = now - days * 86400
        c.execute("SELECT url, title, visit_time FROM browser_history WHERE visit_time >= ? ORDER BY visit_time DESC", (since,))
        rows = c.fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []  # Table might not exist yet
    conn.close()

    formatted = []
    for url, title, visit_time in rows:
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(visit_time))
        formatted.append(f"[{ts_str}] {title} — {url}")
    return formatted
import os
import sqlite3
import time
import shutil
import google.generativeai as genai
from dotenv import load_dotenv
import subprocess
import json
from indexer import extract_text_for_path

# --------------------------------------------------------------------
# 🔧 Setup and Configuration
# --------------------------------------------------------------------
load_dotenv()

VECTORDATA = os.environ.get("VECTORTABLE", "memory_vectors.db")
EVENT_DB = os.environ.get("EVENT_DB", "events.db")

LLM_BACKEND = os.environ.get("LLM_BACKEND", "").lower()  # "gemini" or "ollama"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --------------------------------------------------------------------
# 🧩 Helper Functions
# --------------------------------------------------------------------
def detect_llm_backend():
    """Detect which local LLM is available."""
    if LLM_BACKEND:
        return LLM_BACKEND
    if GEMINI_API_KEY:
        return "gemini"
    if shutil.which("ollama"):
        return "ollama"
    return "stub"

# --------------------------------------------------------------------
# 🤖 Gemini via Official API
# --------------------------------------------------------------------
def gemini_chat(prompt):
    """Run a prompt via Gemini SDK (no CLI)."""
    if not GEMINI_API_KEY:
        return "[Gemini Error] Missing GEMINI_API_KEY in .env file."

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "[Gemini Error] Empty response."
    except Exception as e:
        return f"[Gemini Error] {str(e)}"

# --------------------------------------------------------------------
# 🦙 Ollama (local fallback)
# --------------------------------------------------------------------
def ollama_chat(prompt):
    """Run a prompt via Ollama CLI and return its output."""
    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL, prompt],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[Ollama Error] {str(e)}"

# --------------------------------------------------------------------
# 🧱 Stub Fallback
# --------------------------------------------------------------------
def stub_chat(prompt):
    """Fallback mode for when no LLM is available."""
    return f"[stub] (No LLM connected)\nYou asked: {prompt}"

# --------------------------------------------------------------------
# 📘 File System Memory Context
# --------------------------------------------------------------------
def search_recent_files(db_path, limit=10):
    """Fetch most recent file events for context."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT event_type, path, timestamp FROM events ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()

    formatted = []
    for r in rows:
        event_type, path, ts = r
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        formatted.append(f"[{ts_str}] {event_type.upper()}: {path}")
    return formatted

# --------------------------------------------------------------------
# 🧩 Git Commit Memory Context
# --------------------------------------------------------------------
def search_recent_commits(db_path, limit=5):
    """Fetch most recent git commit events."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute("SELECT repo, commit_hash, author, date, message FROM git_commits ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []  # Table might not exist yet
    conn.close()

    formatted = []
    for repo, commit_hash, author, date, message in rows:
        formatted.append(f"📦 Repo: {repo}\n🔖 Commit: {commit_hash}\n👤 {author} on {date}\n💬 {message}")
    return formatted

# --------------------------------------------------------------------
# 💬 Chat Interface
# --------------------------------------------------------------------
if __name__ == "__main__":
    backend = detect_llm_backend()
    print(f"[LLMClient] backend={backend}")
    print("Local AI Memory Agent — chat (type 'exit' to quit)\n")

    while True:
        query = input("You: ").strip()
        if query.lower() in ["exit", "quit", "bye"]:
            break

        # Quick path request: if the user explicitly asks to share the contents
        # of a specific file, extract and return the file text directly instead
        # of relying on semantic search (which may use stub embeddings).
        lowq = query.lower()
        if lowq.startswith("share the contents of") or lowq.startswith("share the contents"):
            try:
                # naive parse: take everything after the word 'of'
                if ' of ' in lowq:
                    idx = lowq.index(' of ')
                    path = query[idx + 4 :].strip().strip('"\'')
                else:
                    # fallback: last token
                    path = query.split()[-1].strip().strip('"\'')

                # if user provided a basename, try to resolve from recent file events
                if not (os.path.isabs(path) or '\\' in path or '/' in path):
                    recent = search_recent_files(EVENT_DB, limit=50)
                    candidates = [r.split(': ', 1)[1] for r in recent if ': ' in r]
                    matches = [p for p in candidates if os.path.basename(p).lower() == path.lower()]
                    if matches:
                        path = matches[0]

                if not os.path.exists(path):
                    print(f"\nAssistant:\n[Error] file not found: {path}\n")
                else:
                    content = extract_text_for_path(path)
                    if not content:
                        print(f"\nAssistant:\n[No extractable text found in {path}]\n")
                    else:
                        # limit to a reasonable display size
                        display = content[:4000] + ("\n... (truncated)" if len(content) > 4000 else "")
                        print("\nAssistant:\n" + display + "\n")
            except Exception as e:
                print(f"\nAssistant:\n[Error extracting file path: {e}]\n")
            continue



        # Fetch context from all sources
        recent_files = search_recent_files(EVENT_DB, limit=10)
        recent_commits = search_recent_commits(EVENT_DB, limit=5)
        recent_browser = search_recent_browser_history(EVENT_DB, days=2)
        doc_search = semantic_search_documents(query, top_k=3)

        context = ""
        if recent_files:
            context += "📁 Recent file activity:\n" + "\n".join(recent_files) + "\n\n"
        if recent_commits:
            context += "🧩 Recent Git commits:\n" + "\n\n".join(recent_commits) + "\n\n"
        if recent_browser:
            context += "🌐 Recent Browser History:\n" + "\n".join(recent_browser) + "\n\n"
        if doc_search:
            context += "📄 Relevant Document Content:\n" + "\n\n".join(doc_search) + "\n\n"
        if not context:
            context = "No recent file, commit, browser, or document activity logged."

        full_prompt = (
            f"You are a personal memory assistant.\n"
            f"User asked: {query}\n\n"
            f"{context}"
            f"Answer clearly and concisely."
        )

        if backend == "gemini":
            reply = gemini_chat(full_prompt)
        elif backend == "ollama":
            reply = ollama_chat(full_prompt)
        else:
            reply = stub_chat(full_prompt)

        print("\nAssistant:\n" + reply + "\n")
