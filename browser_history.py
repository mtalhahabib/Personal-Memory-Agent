import sqlite3
import os
import shutil
import time

CHROME_HISTORY_PATH = r"C:\Users\Pc planet\AppData\Local\Microsoft\Edge\User Data\Default\History"
EVENT_DB = os.environ.get("EVENT_DB", "events.db")

def fetch_recent_history(db_path=EVENT_DB, days=2):
    # Copy history to avoid locking issues
    TEMP_HISTORY_PATH = "chrome_history_temp.db"
    if os.path.exists(TEMP_HISTORY_PATH):
        os.remove(TEMP_HISTORY_PATH)
    shutil.copy2(CHROME_HISTORY_PATH, TEMP_HISTORY_PATH)

    # Read from Chrome/Edge DB
    conn = sqlite3.connect(TEMP_HISTORY_PATH)
    c = conn.cursor()
    c.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()

    def chrome_time_to_unix(chrome_time):
        return int((chrome_time - 11644473600000000) / 1000000) if chrome_time else 0

    # Save to local events.db
    conn2 = sqlite3.connect(db_path)
    c2 = conn2.cursor()
    c2.execute("""
    CREATE TABLE IF NOT EXISTS browser_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        title TEXT,
        visit_time INTEGER
    )
    """)
    for url, title, visit_time in rows:
        unix_time = chrome_time_to_unix(visit_time)
        c2.execute("INSERT INTO browser_history (url, title, visit_time) VALUES (?, ?, ?)", (url, title, unix_time))
    conn2.commit()
    conn2.close()

    # Return formatted last N days
    since = time.time() - days*86400
    formatted = [f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}] {title} — {url}"
                 for url, title, ts in [(r[0], r[1], chrome_time_to_unix(r[2])) for r in rows] if ts >= since]
    return formatted
