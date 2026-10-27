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
            migrate_events=not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_sequence'").fetchone()
            db.execute('CREATE TABLE IF NOT EXISTS event_sequence(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,job_id TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS event_job_cursor ON event_sequence(job_id,seq)')
            db.execute("CREATE INDEX IF NOT EXISTS regeneration_parent ON entities(kind,json_extract(body,'$.regenerated_from'))")
            db.execute("CREATE INDEX IF NOT EXISTS entity_status ON entities(kind,json_extract(body,'$.status'))")
            db.execute("CREATE INDEX IF NOT EXISTS job_batch ON entities(kind,json_extract(body,'$.batch_id'))")
            db.execute("CREATE INDEX IF NOT EXISTS entity_request_key ON entities(kind,json_extract(body,'$.idempotency_key'))")
            db.execute("CREATE INDEX IF NOT EXISTS recording_workflow ON entities(kind,json_extract(body,'$.smart_reference.status'))")
            db.execute("CREATE INDEX IF NOT EXISTS processing_recording ON entities(kind,json_extract(body,'$.recording_id'))")
            db.execute("CREATE INDEX IF NOT EXISTS processing_parent ON entities(kind,json_extract(body,'$.source_processing_id'))")
            if migrate_events:
                db.execute("INSERT INTO event_sequence(event_id,job_id) SELECT id,json_extract(body,'$.job_id') FROM entities WHERE kind='events' ORDER BY rowid")
            db.execute("PRAGMA user_version=2")

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

    def list(self, kind, include_deleted=False,limit=None,offset=0):
        with self.connect() as db:
            query="SELECT body FROM entities WHERE kind=?"+("" if include_deleted else " AND COALESCE(json_extract(body,'$.deleted_at'),'')=''")+" ORDER BY rowid DESC"
            rows=db.execute(query+(' LIMIT ? OFFSET ?' if limit is not None else ''),(kind,limit,offset) if limit is not None else (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def by_status(self,kind,statuses,limit=None,count=False):
        marks=','.join('?' for _ in statuses)
        query=('SELECT COUNT(*)' if count else 'SELECT body')+" FROM entities WHERE kind=? AND json_extract(body,'$.status') IN ("+marks+") AND COALESCE(json_extract(body,'$.deleted_at'),'')=''"
        args=[kind,*statuses]
        if not count:
            query+=' ORDER BY rowid ASC'
            if limit is not None:query+=' LIMIT ?';args.append(limit)
        with self.connect() as db:rows=db.execute(query,args).fetchall()
        return rows[0][0] if count else [json.loads(row[0]) for row in rows]

    def active_reference_workflows(self):
        with self.connect() as db:
            rows=db.execute("SELECT body FROM entities WHERE kind='recordings' AND json_extract(body,'$.smart_reference.status') IN ('analyzing','processing','analyzing_outputs') AND COALESCE(json_extract(body,'$.deleted_at'),'')='' ").fetchall()
        return [json.loads(row[0]) for row in rows]

    def jobs(self, archived=False, project_id=None, status=None, limit=None, offset=0, batch_id=None):
        clauses=["kind='jobs'", "COALESCE(json_extract(body,'$.deleted_at'),'')=''", "COALESCE(json_extract(body,'$.archived_at'),'') "+("!=''" if archived else "=''")]
        arguments=[]
        for field,value in (('project_id',project_id),('status',status),('batch_id',batch_id)):
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
        item=dict(id=uid(),job_id=job_id,event=event,created_at=now(),**details)
        with self.lock,self.connect() as db:
            db.execute('INSERT INTO entities VALUES (?,?,?)',('events',item['id'],json.dumps(item,ensure_ascii=False)))
            cursor=db.execute('INSERT INTO event_sequence(event_id,job_id) VALUES (?,?)',(item['id'],job_id))
            seq=cursor.lastrowid
        return dict(item,seq=seq)

    def events(self,job_id,after_seq=0,limit=1000):
        with self.connect() as db:
            rows=db.execute("SELECT s.seq,e.body FROM event_sequence s JOIN entities e ON e.kind='events' AND e.id=s.event_id WHERE s.job_id=? AND s.seq>? ORDER BY s.seq LIMIT ?",(job_id,after_seq,limit)).fetchall()
        return [dict(json.loads(body),seq=seq) for seq,body in rows]

    def event_cursor(self,job_id,value):
        if not value:return 0
        if value.isdecimal():return int(value)
        with self.connect() as db:
            row=db.execute('SELECT seq FROM event_sequence WHERE job_id=? AND event_id=?',(job_id,value)).fetchone()
        if not row:raise ValueError('事件游标不属于此任务')
        return row[0]

    def backup(self, destination):
        with self.lock, self.connect() as db, sqlite3.connect(destination) as out:
            db.backup(out)
