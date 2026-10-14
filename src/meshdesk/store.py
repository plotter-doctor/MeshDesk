"""SQLite persistence, scoped to a connection; UI reads bounded result sets."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nodes (profile TEXT, num INTEGER, data TEXT, PRIMARY KEY(profile,num));
            CREATE TABLE IF NOT EXISTS messages (
              rowid INTEGER PRIMARY KEY, profile TEXT, packet_id INTEGER, sender INTEGER,
              destination INTEGER, channel INTEGER, text TEXT, timestamp REAL, status TEXT,
              outgoing INTEGER, read INTEGER DEFAULT 0, metadata TEXT, UNIQUE(profile,packet_id,sender));
            CREATE INDEX IF NOT EXISTS messages_time ON messages(profile,timestamp);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, profile TEXT, kind TEXT, timestamp REAL, data TEXT);
            CREATE TABLE IF NOT EXISTS waypoints (profile TEXT, id INTEGER, data TEXT, PRIMARY KEY(profile,id));
            PRAGMA user_version=1;
        ''')
        self.db.commit()

    def execute(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            rows = cur.fetchall()
            self.db.commit()
            return rows

    def get(self, key, default=None):
        rows = self.execute('SELECT value FROM meta WHERE key=?', (key,))
        return json.loads(rows[0][0]) if rows else default

    def put(self, key, value):
        self.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps(value)))

    def profiles(self):
        return [json.loads(r[0]) for r in self.execute('SELECT data FROM profiles ORDER BY id')]

    def save_profile(self, profile):
        self.execute('INSERT OR REPLACE INTO profiles VALUES (?,?)', (profile['id'], json.dumps(profile)))

    def node(self, profile, data):
        self.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?)', (profile, int(data['num']), json.dumps(data)))

    def nodes(self, profile):
        return [json.loads(r[0]) for r in self.execute('SELECT data FROM nodes WHERE profile=? ORDER BY num', (profile,))]

    def message(self, profile, packet_id, sender, destination, channel, text, timestamp=None, status='received', outgoing=False, metadata=None):
        self.execute('''INSERT INTO messages(profile,packet_id,sender,destination,channel,text,timestamp,status,outgoing,read,metadata)
          VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(profile,packet_id,sender) DO UPDATE SET
          metadata=excluded.metadata''', (profile, int(packet_id), int(sender), int(destination), int(channel), text,
          timestamp or time.time(), status, int(outgoing), int(outgoing), json.dumps(metadata or {})))

    def ack(self, profile, packet_id, status):
        self.execute('UPDATE messages SET status=? WHERE profile=? AND packet_id=? AND outgoing=1', (status, profile, int(packet_id)))

    def messages(self, profile, peer=0, channel=0, search='', limit=100, offset=0):
        condition = 'destination=4294967295 AND channel=?' if not peer else '(sender=? OR destination=?) AND destination!=4294967295'
        args = (channel,) if not peer else (int(peer), int(peer))
        rows = self.execute('SELECT * FROM messages WHERE profile=? AND '+condition+' AND text LIKE ? ORDER BY timestamp DESC,rowid DESC LIMIT ? OFFSET ?',
                            (profile,)+args+('%'+search+'%', min(max(int(limit),1),500), max(int(offset),0)))
        return [dict(r, metadata=json.loads(r['metadata'])) for r in reversed(rows)]

    def mark_read(self, profile, peer=0, channel=0):
        if peer:
            self.execute('UPDATE messages SET read=1 WHERE profile=? AND (sender=? OR destination=?) AND destination!=4294967295', (profile,int(peer),int(peer)))
        else:
            self.execute('UPDATE messages SET read=1 WHERE profile=? AND destination=4294967295 AND channel=?', (profile,int(channel)))

    def unread(self, profile):
        return [dict(r) for r in self.execute('SELECT sender,destination,channel,count(*) AS count FROM messages WHERE profile=? AND read=0 GROUP BY sender,destination,channel',(profile,))]

    def delete_messages(self, profile, peer=0, channel=0):
        if peer:
            self.execute('DELETE FROM messages WHERE profile=? AND (sender=? OR destination=?) AND destination!=4294967295',(profile,int(peer),int(peer)))
        else:
            self.execute('DELETE FROM messages WHERE profile=? AND destination=4294967295 AND channel=?',(profile,int(channel)))

    def event(self, profile, kind, data):
        self.execute('INSERT INTO events(profile,kind,timestamp,data) VALUES (?,?,?,?)',(profile,kind,time.time(),json.dumps(data)))
        # Keep diagnostics bounded on devices with little storage.
        self.execute('DELETE FROM events WHERE profile=? AND id NOT IN (SELECT id FROM events WHERE profile=? ORDER BY id DESC LIMIT 2000)',(profile,profile))

    def events(self, profile, limit=200):
        return [dict(r, data=json.loads(r['data'])) for r in self.execute('SELECT * FROM events WHERE profile=? ORDER BY id DESC LIMIT ?',(profile,limit))]

    def clear_profile(self, profile):
        for table in ('nodes','messages','events','waypoints'):
            self.execute('DELETE FROM '+table+' WHERE profile=?',(profile,))
        self.execute('DELETE FROM meta WHERE key=?',('snapshot:'+profile,))

    def clear_all(self):
        with self.lock,self.db:
            for table in ('profiles','nodes','messages','events','waypoints','meta'):
                self.db.execute('DELETE FROM '+table)

    def waypoint(self, profile, waypoint, sender):
        existing=self.execute('SELECT data FROM waypoints WHERE profile=? AND id=?',(profile,int(waypoint['id'])))
        old=json.loads(existing[0][0]) if existing else {}
        locked=old.get('lockedTo',old.get('locked_to',0))
        if locked and int(locked)!=int(sender):return
        data=dict(waypoint,created=old.get('created',time.time()),updated=time.time(),sender=sender)
        self.execute('INSERT OR REPLACE INTO waypoints VALUES (?,?,?)',(profile,int(waypoint['id']),json.dumps(data)))

    def waypoints(self, profile):
        now=time.time()
        return [data for row in self.execute('SELECT data FROM waypoints WHERE profile=?',(profile,))
                if not (data:=json.loads(row[0])).get('expire') or int(data['expire'])>now]

    def close(self):
        with self.lock:
            self.db.close()
