import os
import sqlite3
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

# Databases
EVENT_DB = os.environ.get("EVENT_DB", "events.db")
GIT_AUTO_DISCOVER = os.environ.get("GIT_AUTO_DISCOVER", "true").lower() == "true"
BASE_PATHS = [p.strip() for p in os.environ.get("WATCH_PATHS", "").split(",") if p.strip()]
GIT_WATCH_PATHS = [p.strip() for p in os.environ.get("GIT_WATCH_PATHS", "").split(",") if p.strip()]

def discover_git_repos(start_path):
    """Recursively discover git repositories under a path."""
    git_repos = []
    
    # print(f"[git_watcher] Scanning directory: {start_path}")
    try:
        for root, dirs, _ in os.walk(start_path):
            if '.git' in dirs:
                # This is a git repository
                repo_path = root
                try:
                    # Verify it's a valid git repo by running a git command
                    # print(f"[git_watcher] Found potential git repo: {repo_path}")
                    subprocess.check_output(['git', '-C', repo_path, 'rev-parse', '--git-dir'], 
                                         stderr=subprocess.DEVNULL)
                    # print(f"[git_watcher] Confirmed valid git repo: {repo_path}")
                    git_repos.append(repo_path)
                    # Don't recurse into this repo's subdirectories
                    dirs.remove('.git')
                except subprocess.CalledProcessError:
                    print(f"[git_watcher] Invalid git repo: {repo_path}")
                    pass  # Not a valid git repo
            
            # Skip common large directories that won't contain repos
            for skip in ['.venv', 'node_modules', '__pycache__', 'build', 'dist']:
                if skip in dirs:
                    dirs.remove(skip)
                    
    except Exception as e:
        print(f"[git_watcher] Error scanning {start_path}: {e}")
    
    return git_repos

# Poll interval in seconds
POLL_INTERVAL = 30  # check every 30 seconds

def init_db():
    conn = sqlite3.connect(EVENT_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS git_commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT,            -- Full path to repo
            repo_name TEXT,       -- Name of repo (last component of path)
            repo_dir TEXT,        -- Directory containing repo
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
    
    # Track all repositories we'll scan
    repos_to_scan = set()
    
    # Add explicitly configured paths
    for path in GIT_WATCH_PATHS:
        path = path.strip()
        if path:  # Skip empty paths
            repos_to_scan.add(os.path.abspath(path))
    
    # Auto-discover repositories if enabled
    if GIT_AUTO_DISCOVER:
        base_paths = BASE_PATHS if BASE_PATHS else [os.getcwd()]  # Use current dir if no paths specified
        for base in base_paths:
            if os.path.isdir(base):
                discovered = discover_git_repos(base)
                repos_to_scan.update(discovered)
    
    # Scan each repository
    for path in repos_to_scan:
        git_dir = os.path.join(path, ".git")
        if not os.path.isdir(git_dir):
            continue
            
        try:
            commits = extract_commit_history(path)
            for commit in commits:
                # Check if commit is already in DB
                c.execute("SELECT 1 FROM git_commits WHERE commit_hash=? AND repo=?", 
                         (commit["hash"], path))
                if not c.fetchone():
                    # Get repository name and directory
                    repo_name = os.path.basename(path.rstrip('\\')).rstrip('/')
                    repo_dir = os.path.dirname(path)
                    
                    c.execute("""
                        INSERT INTO git_commits (
                            repo, repo_name, repo_dir, commit_hash, 
                            author, date, message, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (path, repo_name, repo_dir, commit["hash"], 
                         commit["author"], commit["date"], 
                         commit["message"], time.time()))
                    conn.commit()
                    print(f"[git_watcher] New commit logged: {commit['message']} ({path})")
        except Exception as e:
            print(f"[git_watcher] Error processing repo {path}: {e}")

if __name__ == "__main__":
    conn = init_db()
    print(f"[git_watcher] Starting git commit watcher...")
    print(f"[git_watcher] Auto-discovery: {'enabled' if GIT_AUTO_DISCOVER else 'disabled'}")

    # Show explicit paths
    if GIT_WATCH_PATHS:
        print("[git_watcher] Explicit watch paths:")
        for p in GIT_WATCH_PATHS:
            print(f"  - {p}")
    
    # Show auto-discovered repositories
    if GIT_AUTO_DISCOVER:
        print("\n[git_watcher] Base paths for repository discovery:")
        for p in (BASE_PATHS if BASE_PATHS else [os.getcwd()]):
            print(f"  - {p}")

        all_repos = set()
        for base in (BASE_PATHS if BASE_PATHS else [os.getcwd()]):
            if os.path.isdir(base):
                discovered = discover_git_repos(base)
                all_repos.update(discovered)
        
        if all_repos:
            print("\n[git_watcher] Discovered git repositories:")
            for repo in sorted(all_repos):
                print(f"  - {repo}")
        else:
            print("\n[git_watcher] No git repositories found in watch paths")
    
    try:
        print("\n[git_watcher] Starting commit monitoring (Ctrl+C to stop)...")
        while True:
            scan_repos(conn)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[git_watcher] Stopped.")
