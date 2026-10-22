import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return str(uuid.uuid4())

class Store:
    """JSON entities in transactional SQLite. Connections never cross threads."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "platform.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS entities (kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id))")
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, kind, item):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO entities VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body", (kind, item["id"], json.dumps(item, ensure_ascii=False)))
        return item

    def get(self, kind, identity):
        with self.connect() as db:
            row = db.execute("SELECT body FROM entities WHERE kind=? AND id=?", (kind, identity)).fetchone()
        if row is None:
            raise KeyError(f"{kind} 不存在: {identity}")
        return json.loads(row[0])

    def list(self, kind, include_deleted=False):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM entities WHERE kind=?"+("" if include_deleted else " AND COALESCE(json_extract(body,'$.deleted_at'),'')=''")+" ORDER BY rowid DESC", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def jobs(self, archived=False, project_id=None, status=None, limit=None, offset=0):
        clauses=["kind='jobs'", "COALESCE(json_extract(body,'$.deleted_at'),'')=''", "COALESCE(json_extract(body,'$.archived_at'),'') "+("!=''" if archived else "=''")]
        arguments=[]
        for field,value in (('project_id',project_id),('status',status)):
            if value:
                clauses.append(f"json_extract(body,'$.{field}')=?");arguments.append(value)
        where=' AND '.join(clauses)
        with self.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM entities WHERE '+where,arguments).fetchone()[0]
            sort="json_extract(body,'$.archived_at')" if archived else "COALESCE(json_extract(body,'$.restored_at'),json_extract(body,'$.created_at'))"
            query='SELECT body FROM entities WHERE '+where+' ORDER BY '+sort+' DESC,rowid DESC'
            if limit is not None:query+=' LIMIT ? OFFSET ?';arguments += [limit,offset]
            rows=db.execute(query,arguments).fetchall()
        return dict(items=[json.loads(row[0]) for row in rows],total=total)

    def update(self, kind, identity, **changes):
        with self.lock:
            item = self.get(kind, identity)
            item.update(changes, updated_at=now())
            return self.save(kind, item)

    def event(self, job_id, event, **details):
        return self.save("events", dict(id=uid(), job_id=job_id, event=event, created_at=now(), **details))

    def backup(self, destination):
        with self.lock, self.connect() as db, sqlite3.connect(destination) as out:
            db.backup(out)
