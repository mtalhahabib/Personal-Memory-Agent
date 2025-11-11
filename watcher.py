import time
import os
import sqlite3
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

load_dotenv()
WATCH_PATHS = os.environ.get('WATCH_PATHS', '').split(",")
EXCLUDE_PATTERNS = [e.strip().lower() for e in os.environ.get('EXCLUDE_PATTERNS', '').split(",")]
EVENT_DB = os.environ.get('EVENT_DB', 'events.db')

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

def safe_insert_event(conn, t, path, ts, retries=5, delay=0.1):
    for _ in range(retries):
        try:
            c = conn.cursor()
            c.execute("INSERT INTO events (event_type, path, timestamp) VALUES (?, ?, ?)", (t, path, ts))
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                time.sleep(delay)
            else:
                raise
    return False

class Handler(FileSystemEventHandler):
    def __init__(self, conn):
        self.conn = conn
    def on_any_event(self, event):
        if event.is_directory: return
        path = event.src_path
        if any(ex in path.lower() for ex in EXCLUDE_PATTERNS): return
        if path.endswith(".db") or path.endswith(".db-journal"): return
        safe_insert_event(self.conn, event.event_type, path, time.time())

if __name__ == '__main__':
    conn = init_db()
    observers = []
    for p in WATCH_PATHS:
        p = os.path.expanduser(p)
        if not os.path.exists(p): continue
        obs = Observer()
        obs.schedule(Handler(conn), p, recursive=True)
        obs.start()
        observers.append(obs)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for o in observers: o.stop()
        for o in observers: o.join()
