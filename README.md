# 🧠 Personal Memory Agent

A **local AI memory system** that keeps track of your **file activity**, **browser history**, **Notes** and **Git commits**, and lets you **chat** with your digital memory using **Gemini CLI** or **Ollama (Llama3)**.  
Fully offline. Privacy-safe. Extendable.

---

## 🚀 Overview

This project turns your local machine into a personal memory assistant that can:
- 📂 Track all file creations, modifications, and deletions.
- 🧾 Log new Git commits across repositories.
- 🧾 Check all the browser history
- Chat with you Notes
- 💬 Chat naturally about your recent activity using local LLMs.
- 🔒 Store everything locally in SQLite databases for full privacy.


---

## 🧰 Tech Stack

| Component | Description |
|------------|-------------|
| **Python 3.10+** | Core scripting and logic |
| **SQLite** | Local persistent memory database |
| **Watchdog** | File system event listener |
| **Gemini CLI** | Local LLM integration |
| **Ollama (Llama3)** | Offline LLM alternative |
| **dotenv** | Environment configuration loader |

---

## ⚙️ Setup Guide

```bash
# 1️⃣ Clone and prepare environment
git clone https://github.com/your-username/Personal-Memory-Agent.git
cd Personal-Memory-Agent
python -m venv .venv
.venv\Scripts\activate   # for Windows
# or
source .venv/bin/activate  # for macOS/Linux
pip install -r requirements.txt
```


Create a .env file in the project root with:
bash
Copy code

```
# 🧭 Paths to watch (comma-separated)
WATCH_PATHS=E:\CodeAcm

# 🧭 Git Paths to watch (comma-separated)
GIT_WATCH_PATHS=E:\CodeAcm\CodeAcme Repos\realEstate_frontend_livekit

# 🚫 Excluded folders or patterns
EXCLUDE_PATTERNS=.git,node_modules,__pycache__,.venv,.idea

# 🤖 LLM backend (gemini | ollama)
LLM_BACKEND=gemini

# 💬 Model configurations
GEMINI_MODEL=gemini-1.5-flash
OLLAMA_MODEL=llama3

# 🔑 Gemini API key (required if using Gemini API)
GEMINI_API_KEY=your_api_key_here

# 🧠 Databases
VECTOR_DB=memory_vectors.db
EVENT_DB=events.db

# ⚙️ Watcher debounce time
DEBOUNCE_SEC=0.4
Install Gemini CLI for LLM access:
```



🧩 Running the System
bash
Copy code
```
Run all these commands in separate terminals
# 🗂️ Watch local file system for changes
python watcher.py

# 🧾 Monitor Git repositories for new commits
python git_watcher.py

# Run your Indexer file
python indexer.py

# 💬 Chat with your local memory
python chat.py

```
## 📁 Data Storage
All data is stored locally in SQLite databases:

## Database	Purpose
events.db	Tracks file system events and Git commits
memory_vectors.db	Stores semantic memory embeddings (for LLM search)

## 🔒 Privacy First
This project runs entirely locally.
No data is uploaded, transmitted, or logged externally.
Your system’s memory remains 100% private and under your control.

## 🧭 Future Extensions
Planned improvements include:

🗒️ Local note ingestion (auto-summary + retrieval)

🌐 Browser history context memory


🧬 Enhanced embedding search (via Ollama or Gemini embeddings)

##💬 Example Interaction
bash
Copy code
```
(.venv) PS E:\CodeAcm\Personal Memory Agent> python chat.py
[LLMClient] backend=gemini
Local AI Memory Agent — chat (type 'exit' to quit)

You: What files did I recently modify?
Assistant:
- [2025-11-05 10:32:44] MODIFIED: report_draft.txt
- [2025-11-05 09:50:11] CREATED: project_notes.md
- [2025-11-05 09:20:30] COMMIT: "Refactored data model in realEstate_frontend"

```

Ask the questions from the bot like:
- List down all the urls of sites which i visited today.  (From Browser History)
- Provide me the summary of my activity of my files and folders which i modfied recently
- Please provide me the git commit history of my following repo(repo path or name)
