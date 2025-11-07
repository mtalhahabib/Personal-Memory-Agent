import sqlite3
import os
import shutil
from datetime import datetime

CHROME_HISTORY_PATH = r"C:\Users\Pc planet\AppData\Local\Google\Chrome\User Data\Default\History"
EVENT_DB = os.environ.get("EVENT_DB", "events.db")

# Copy Chrome history file to avoid locking issues
TEMP_HISTORY_PATH = "chrome_history_temp.db"
if os.path.exists(TEMP_HISTORY_PATH):
    os.remove(TEMP_HISTORY_PATH)
shutil.copy2(CHROME_HISTORY_PATH, TEMP_HISTORY_PATH)

# Connect to Chrome history SQLite
conn = sqlite3.connect(TEMP_HISTORY_PATH)
c = conn.cursor()
c.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 100")
rows = c.fetchall()
conn.close()

# Convert Chrome timestamp to Unix timestamp
def chrome_time_to_unix(chrome_time):
    # Chrome timestamp is microseconds since Jan 1, 1601
    if not chrome_time:
        return 0
    return int((chrome_time - 11644473600000000) / 1000000)

# Create browser_history table in events.db
conn2 = sqlite3.connect(EVENT_DB)
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

print(f"Imported {len(rows)} browser history records into events.db.")
