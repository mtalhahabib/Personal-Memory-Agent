# chat.py
# --------------------------------------------------------------------
# Professional AI Memory Assistant with context-aware memory
# --------------------------------------------------------------------
import os
import time
import shutil
import sqlite3
import subprocess
from dotenv import load_dotenv
from vectorstore import VectorStore
from llm_client import LLMClient
from indexer import extract_text_for_path
import browser_history
import git_watcher

# --------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------
load_dotenv()
EVENT_DB = os.environ.get("EVENT_DB", "events.db")
VECTOR_DB = os.environ.get("VECTOR_DB", "memory_vectors.db")
SESSION_MEMORY_SIZE = 10  # Last N Q&A pairs to keep for context
MAX_REPLY_LENGTH = 4000  # Max chars to show from LLM or files

# LLM backend
LLM_BACKEND = os.environ.get("LLM_BACKEND", "").lower()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --------------------------------------------------------------------
# Backend detection
# --------------------------------------------------------------------
def detect_llm_backend():
    if LLM_BACKEND:
        return LLM_BACKEND
    if GEMINI_API_KEY:
        return "gemini"
    if shutil.which("ollama"):
        return "ollama"
    return "stub"

backend = detect_llm_backend()
print(f"[LLMClient] backend={backend}")
print("Professional AI Memory Assistant — type 'exit' to quit.\n")

# --------------------------------------------------------------------
# Session memory
# --------------------------------------------------------------------
session_memory = []  # Stores list of {"user": "...", "assistant": "..."}

def add_to_session(user_query, assistant_reply):
    session_memory.append({"user": user_query, "assistant": assistant_reply})
    if len(session_memory) > SESSION_MEMORY_SIZE:
        session_memory.pop(0)

def get_session_context():
    """Return formatted string of recent session memory"""
    context = ""
    for pair in session_memory:
        context += f"User: {pair['user']}\nAssistant: {pair['assistant']}\n"
    return context

# --------------------------------------------------------------------
# LLM interface
# --------------------------------------------------------------------
def gemini_chat(prompt):
    import google.generativeai as genai
    if not GEMINI_API_KEY:
        return "[Gemini Error] Missing GEMINI_API_KEY"
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "[Gemini Error] Empty response."
    except Exception as e:
        return f"[Gemini Error] {str(e)}"

def ollama_chat(prompt):
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

def stub_chat(prompt):
    return f"[stub] (No LLM connected)\nYou asked: {prompt}"

def run_llm(prompt):
    if backend == "gemini":
        return gemini_chat(prompt)
    elif backend == "ollama":
        return ollama_chat(prompt)
    else:
        return stub_chat(prompt)

# --------------------------------------------------------------------
# Semantic search
# --------------------------------------------------------------------
def semantic_search_documents(query, top_k=3):
    vs = VectorStore()
    client = LLMClient()
    query_emb = client.embed([query])[0]
    results = vs.search(query_emb, top_k=top_k)
    formatted = []
    for score, meta in results:
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(meta['timestamp']))
        formatted.append(f"[{ts_str}] {meta['summary']}\n(path: {meta['path']}, score: {score:.2f})")
    return formatted

# --------------------------------------------------------------------
# Recent file activity
# --------------------------------------------------------------------
def search_recent_files(db_path, limit=10):
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
# Recent browser history
# --------------------------------------------------------------------
def search_recent_browser_history(db_path, days=2):
    try:
        return browser_history.fetch_recent_history(db_path, days)
    except Exception:
        return []

# --------------------------------------------------------------------
# Git repositories & commits
# --------------------------------------------------------------------
def list_all_repositories():
    base_paths = [p.strip() for p in os.environ.get("WATCH_PATHS", "").split(",") if p.strip()]
    if not base_paths:
        base_paths = [os.path.dirname(os.path.dirname(os.getcwd()))]
    
    all_repos = []
    for path in base_paths:
        if os.path.exists(path):
            repos = git_watcher.discover_git_repos(path)
            all_repos.extend(repos)

    seen = set()
    unique_repos = []
    for repo in all_repos:
        if repo not in seen:
            seen.add(repo)
            unique_repos.append(repo)
    
    formatted = []
    for repo_path in unique_repos:
        repo_name = os.path.basename(repo_path.rstrip('\\')).rstrip('/')
        repo_dir = os.path.dirname(repo_path)
        formatted.append(f"\n📦 Repository: {repo_name}")
        formatted.append(f"📂 Directory: {repo_dir}")
    return formatted

def search_recent_commits(db_path, limit=5):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    formatted = []
    try:
        c.execute("SELECT DISTINCT repo FROM git_commits ORDER BY repo")
        repos = c.fetchall()
        for (repo_path,) in repos:
            c.execute("""
                SELECT repo_name, repo_dir, commit_hash, author, date, message 
                FROM git_commits 
                WHERE repo = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (repo_path, limit))
            commits = c.fetchall()
            if not commits:
                continue
            repo_name, repo_dir = commits[0][:2]
            formatted.append(f"\n📦 Repository: {repo_name}")
            formatted.append(f"📂 Directory: {repo_dir}")
            for _, _, commit_hash, author, date, message in commits:
                formatted.append(f"  🔖 {commit_hash[:8]}")
                formatted.append(f"  👤 {author} on {date}")
                formatted.append(f"  💬 {message}\n")
    except sqlite3.OperationalError:
        pass
    conn.close()
    return formatted

# --------------------------------------------------------------------
# File content extraction
# --------------------------------------------------------------------
def extract_file_content(file_name):
    if not os.path.isabs(file_name):
        recent_files = search_recent_files(EVENT_DB, limit=50)
        candidates = [r.split(': ',1)[1] for r in recent_files if ': ' in r]
        matches = [p for p in candidates if os.path.basename(p).lower() == file_name.lower()]
        if matches:
            file_name = matches[0]
    if not os.path.exists(file_name):
        return f"[Error] file not found: {file_name}"
    content = extract_text_for_path(file_name)
    return content[:MAX_REPLY_LENGTH] + ("\n... (truncated)" if len(content) > MAX_REPLY_LENGTH else "")

# --------------------------------------------------------------------
# Chat loop
# --------------------------------------------------------------------
def main():
    while True:
        user_query = input("You: ").strip()
        if user_query.lower() in ["exit", "quit", "bye"]:
            print("Goodbye!")
            break

        # File extraction command
        if user_query.lower().startswith("share the contents"):
            try:
                file_name = user_query.split(" of ")[-1].strip().strip('"\'')
                reply = extract_file_content(file_name)
                print("\nAssistant:\n" + reply + "\n")
                add_to_session(user_query, reply)
                continue
            except Exception as e:
                reply = f"[Error extracting file: {e}]"
                print("\nAssistant:\n" + reply + "\n")
                add_to_session(user_query, reply)
                continue

        # Fetch context
        recent_files = search_recent_files(EVENT_DB, limit=10)
        recent_commits = search_recent_commits(EVENT_DB, limit=5)
        recent_browser = search_recent_browser_history(EVENT_DB, days=2)
        doc_search = semantic_search_documents(user_query, top_k=3)
        all_repos = list_all_repositories()

        # Build context string
        context = get_session_context() + "\n"
        if all_repos:
            context += "📦 All Git repositories:\n" + "\n".join(all_repos) + "\n\n"
        if recent_files:
            context += "📁 Recent file activity:\n" + "\n".join(recent_files) + "\n\n"
        if recent_commits:
            context += "🧩 Recent Git commits:\n" + "\n\n".join(recent_commits) + "\n\n"
        if recent_browser:
            context += "🌐 Recent Browser History:\n" + "\n".join(recent_browser) + "\n\n"
        if doc_search:
            context += "📄 Relevant Document Content:\n" + "\n\n".join(doc_search) + "\n\n"
        if not context.strip():
            context = "No repositories or recent activity available."

        full_prompt = (
            f"You are a professional AI assistant with memory.\n"
            f"Answer concisely, using all available context.\n\n"
            f"Context:\n{context}\n"
            f"User asked: {user_query}\n"
        )

        # Run LLM
        reply = run_llm(full_prompt)
        print("\nAssistant:\n" + reply + "\n")
        add_to_session(user_query, reply)

if __name__ == "__main__":
    main()
