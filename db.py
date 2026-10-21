import sqlite3, time

class DB:
    def __init__(self, path="bot.db"):
        self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row
        self.c.execute("""CREATE TABLE IF NOT EXISTS friends(
            uid TEXT PRIMARY KEY, name TEXT, channel_id INTEGER,
            active INTEGER DEFAULT 1, added_at REAL)""")
        self.c.commit()

    def get(self, uid):
        return self.c.execute("SELECT * FROM friends WHERE uid=?", (uid,)).fetchone()

    def upsert(self, uid, name, channel_id):
        self.c.execute("""INSERT INTO friends(uid,name,channel_id,active,added_at)
            VALUES(?,?,?,1,?) ON CONFLICT(uid) DO UPDATE SET
            name=excluded.name, channel_id=excluded.channel_id, active=1""",
            (uid, name, channel_id, time.time()))
        self.c.commit()

    def deactivate(self, uid):
        self.c.execute("UPDATE friends SET active=0 WHERE uid=?", (uid,))
        self.c.commit()

    def active(self):
        return self.c.execute("SELECT * FROM friends WHERE active=1 ORDER BY name").fetchall()

    def all(self):
        return self.c.execute("SELECT * FROM friends ORDER BY active DESC, name").fetchall()
