import os
import sqlite3
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

# Databases
EVENT_DB = os.environ.get("EVENT_DB", "events.db")
WATCH_PATHS = [p.strip() for p in os.environ.get("GIT_WATCH_PATHS", "").split(",") if p.strip()]

# Poll interval in seconds
POLL_INTERVAL = 30  # check every 30 seconds

def init_db():
    conn = sqlite3.connect(EVENT_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS git_commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT,
            commit_hash TEXT,
            author TEXT,
            date TEXT,
            message TEXT,
            timestamp REAL
        )
    """)
    conn.commit()
    return conn

def get_latest_commit(repo_path):
    """Get latest commit hash for a git repo."""
    try:
        out = subprocess.check_output(["git", "-C", repo_path, "rev-parse", "HEAD"], text=True).strip()
        return out
    except subprocess.CalledProcessError:
        return None

def get_commit_details(repo_path, commit_hash):
    """Get details of a specific commit."""
    try:
        result = subprocess.check_output(
            ["git", "-C", repo_path, "show", "-s", "--format=%H|%an|%ad|%s", commit_hash],
            text=True
        ).strip()
        parts = result.split("|")
        if len(parts) == 4:
            return {
                "hash": parts[0],
                "author": parts[1],
                "date": parts[2],
                "message": parts[3],
            }
    except subprocess.CalledProcessError:
        pass
    return None

def extract_commit_history(repo_path):
    """Extract all commit history for a repo."""
    try:
        result = subprocess.check_output(
            ["git", "-C", repo_path, "log", "--pretty=format:%H|%an|%ad|%s"],
            text=True
        )
        commits = []
        for line in result.splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits
    except subprocess.CalledProcessError:
        return []

def scan_repos(conn):
    """Check all watched paths for git commits and log new ones."""
    c = conn.cursor()
    for path in WATCH_PATHS:
        path = path.strip()
        git_dir = os.path.join(path, ".git")
        if not os.path.isdir(git_dir):
            continue

        commits = extract_commit_history(path)
        for commit in commits:
            # Check if commit is already in DB
            c.execute("SELECT 1 FROM git_commits WHERE commit_hash=? AND repo=?", (commit["hash"], path))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO git_commits (repo, commit_hash, author, date, message, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (path, commit["hash"], commit["author"], commit["date"], commit["message"], time.time()))
                conn.commit()
                print(f"[git_watcher] New commit logged: {commit['message']} ({path})")

if __name__ == "__main__":
    conn = init_db()
    print("[git_watcher] Watching for new Git commits...")
    try:
        while True:
            scan_repos(conn)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[git_watcher] Stopped.")
