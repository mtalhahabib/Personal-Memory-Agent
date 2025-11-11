import os
import sqlite3
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()
EVENT_DB = os.environ.get("EVENT_DB", "events.db")
GIT_AUTO_DISCOVER = os.environ.get("GIT_AUTO_DISCOVER", "true").lower() == "true"
BASE_PATHS = [p.strip() for p in os.environ.get("WATCH_PATHS", "").split(",") if p.strip()]
GIT_WATCH_PATHS = [p.strip() for p in os.environ.get("GIT_WATCH_PATHS", "").split(",") if p.strip()]

POLL_INTERVAL = 30

def discover_git_repos(start_path):
    git_repos = []
    try:
        for root, dirs, _ in os.walk(start_path):
            if ".git" in dirs:
                try:
                    subprocess.check_output(["git", "-C", root, "rev-parse", "--git-dir"], stderr=subprocess.DEVNULL)
                    git_repos.append(root)
                    dirs.remove(".git")
                except subprocess.CalledProcessError:
                    continue
            for skip in [".venv", "node_modules", "__pycache__", "build", "dist"]:
                if skip in dirs:
                    dirs.remove(skip)
    except Exception:
        pass
    return git_repos

def init_db():
    conn = sqlite3.connect(EVENT_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS git_commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT,
            repo_name TEXT,
            repo_dir TEXT,
            commit_hash TEXT,
            author TEXT,
            date TEXT,
            message TEXT,
            timestamp REAL
        )
    """)
    conn.commit()
    return conn

def extract_commit_history(repo_path):
    try:
        result = subprocess.check_output(["git", "-C", repo_path, "log", "--pretty=format:%H|%an|%ad|%s"], text=True)
        commits = []
        for line in result.splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                commits.append({"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]})
        return commits
    except subprocess.CalledProcessError:
        return []

def scan_repos(conn):
    c = conn.cursor()
    repos_to_scan = set(GIT_WATCH_PATHS)
    if GIT_AUTO_DISCOVER:
        for base in BASE_PATHS or [os.getcwd()]:
            if os.path.isdir(base):
                repos_to_scan.update(discover_git_repos(base))
    for path in repos_to_scan:
        commits = extract_commit_history(path)
        for commit in commits:
            c.execute("SELECT 1 FROM git_commits WHERE commit_hash=? AND repo=?", (commit["hash"], path))
            if not c.fetchone():
                repo_name = os.path.basename(path.rstrip("\\")).rstrip("/")
                repo_dir = os.path.dirname(path)
                c.execute("""INSERT INTO git_commits (repo, repo_name, repo_dir, commit_hash, author, date, message, timestamp)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (path, repo_name, repo_dir, commit["hash"], commit["author"], commit["date"], commit["message"], time.time()))
                conn.commit()

if __name__ == "__main__":
    conn = init_db()
    while True:
        scan_repos(conn)
        time.sleep(POLL_INTERVAL)
