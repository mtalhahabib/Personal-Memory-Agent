import time
import os
import sqlite3
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
WATCH_PATHS = os.environ.get('WATCH_PATHS', '')
EXCLUDE_PATTERNS = os.environ.get('EXCLUDE_PATTERNS', '')
EVENT_DB = os.environ.get('EVENT_DB', 'events.db')

# Prepare watch list
if WATCH_PATHS:
    WATCH_PATHS = [p.strip() for p in WATCH_PATHS.split(',') if p.strip()]
else:
    WATCH_PATHS = [os.path.expanduser('~')]  # Default: user home directory

# Prepare exclude patterns
EXCLUDES = [e.strip().lower() for e in EXCLUDE_PATTERNS.split(',') if e.strip()]

# ---------- SQLite Setup ----------
def init_db():
    conn = sqlite3.connect(EVENT_DB, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY,
        event_type TEXT,
        path TEXT,
        timestamp REAL,
        processed INTEGER DEFAULT 0
    )''')
    conn.commit()
    return conn


# ---------- Safe insert with retry ----------
def safe_insert_event(conn, t, path, ts, retries=5, delay=0.1):
    for i in range(retries):
        try:
            c = conn.cursor()
            c.execute(
                'INSERT INTO events (event_type, path, timestamp) VALUES (?, ?, ?)',
                (t, path, ts)
            )
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                time.sleep(delay)
            else:
                raise
    print(f"[watcher] Failed to insert event after {retries} retries → {path}")
    return False


# ---------- Event Handler ----------
class Handler(FileSystemEventHandler):
    def __init__(self, conn):
        self.conn = conn

    def on_any_event(self, event):
        if event.is_directory:
            return

        path = event.src_path

        # Skip excluded paths
        for ex in EXCLUDES:
            if ex and ex in path.lower():
                return

        # Skip database and log files
        if path.endswith('.db') or path.endswith('.db-journal'):
            return

        t = event.event_type
        ts = time.time()

        ok = safe_insert_event(self.conn, t, path, ts)
        if ok:
            print(f"[watcher] {t.upper()} → {path}")


# ---------- Main loop ----------
if __name__ == '__main__':
    conn = init_db()
    observers = []

    for p in WATCH_PATHS:
        p = os.path.expanduser(p)
        if not os.path.exists(p):
            print('[watcher] Skipping non-existent path:', p)
            continue

        handler = Handler(conn)
        obs = Observer()
        obs.schedule(handler, p, recursive=True)
        obs.start()
        observers.append(obs)
        print('[watcher] Watching:', p)

    try:
        print("[watcher] Running... Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[watcher] Stopping watchers...")
        for o in observers:
            o.stop()
        for o in observers:
            o.join()
        print("[watcher] Shutdown complete.")
