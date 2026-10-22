"""Indexed long-form ledger. No book text or segment audio is loaded as a collection."""
import json
from .store import now

class LongformStore:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS lf_books (
              id TEXT PRIMARY KEY, body TEXT NOT NULL, phase TEXT NOT NULL, state TEXT NOT NULL,
              chars INTEGER DEFAULT 0, chapters INTEGER DEFAULT 0, segments INTEGER DEFAULT 0,
              done INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, active_chapter INTEGER,
              created_at TEXT NOT NULL, error TEXT);
            CREATE INDEX IF NOT EXISTS lf_books_queue ON lf_books(phase,state,created_at);
            CREATE TABLE IF NOT EXISTS lf_chapters (
              book_id TEXT NOT NULL, no INTEGER NOT NULL, title TEXT NOT NULL, chars INTEGER DEFAULT 0,
              segments INTEGER DEFAULT 0, done INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
              revision INTEGER DEFAULT 0, review TEXT DEFAULT 'pending', review_version INTEGER DEFAULT 0,
              review_note TEXT DEFAULT '', reviewer TEXT DEFAULT '', reviewed_at TEXT,
              PRIMARY KEY(book_id,no));
            CREATE TABLE IF NOT EXISTS lf_segments (
              book_id TEXT NOT NULL, no INTEGER NOT NULL, chapter_no INTEGER NOT NULL,
              chapter_pos INTEGER NOT NULL, start_byte INTEGER NOT NULL, end_byte INTEGER NOT NULL,
              chars INTEGER NOT NULL, text_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              attempt INTEGER DEFAULT 0, variant INTEGER DEFAULT 0, take TEXT, error TEXT, updated_at TEXT,
              PRIMARY KEY(book_id,no));
            CREATE INDEX IF NOT EXISTS lf_segment_queue ON lf_segments(book_id,status,no);
            CREATE INDEX IF NOT EXISTS lf_segment_chapter ON lf_segments(book_id,chapter_no,no);
            CREATE INDEX IF NOT EXISTS lf_segment_chapter_queue ON lf_segments(book_id,chapter_no,status,no);
            CREATE TABLE IF NOT EXISTS lf_attempts (
              book_id TEXT NOT NULL, segment_no INTEGER NOT NULL, attempt INTEGER NOT NULL, body TEXT NOT NULL,
              PRIMARY KEY(book_id,segment_no,attempt));
            CREATE TABLE IF NOT EXISTS lf_reviews (id TEXT PRIMARY KEY,book_id TEXT,chapter_no INTEGER,revision INTEGER,body TEXT);
            CREATE INDEX IF NOT EXISTS lf_review_history ON lf_reviews(book_id,chapter_no,revision);
            CREATE TABLE IF NOT EXISTS lf_exports (
              id TEXT PRIMARY KEY, book_id TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS lf_export_queue ON lf_exports(state,created_at);
            ''')
            for table in ['lf_books','lf_chapters','lf_segments','lf_exports']:
                if 'deleted_batch' not in {r[1] for r in db.execute('PRAGMA table_info('+table+')')}:
                    db.execute('ALTER TABLE '+table+' ADD COLUMN deleted_batch TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS lf_live_queue ON lf_segments(book_id,deleted_batch,status,no)')
            db.execute('CREATE INDEX IF NOT EXISTS lf_live_chapter_queue ON lf_segments(book_id,chapter_no,deleted_batch,status,no)')
    def book(self,identity):
        with self.store.connect() as db:row=db.execute('SELECT * FROM lf_books WHERE id=?',(identity,)).fetchone();names=[d[1] for d in db.execute('PRAGMA table_info(lf_books)')]
        if row is None:raise KeyError('长文作品不存在')
        item=dict(zip(names,row));body=json.loads(item.pop('body'));return {**body,**item}
    def books(self,limit=20,offset=0):
        with self.store.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM lf_books WHERE deleted_batch IS NULL').fetchone()[0]
            ids=[r[0] for r in db.execute('SELECT id FROM lf_books WHERE deleted_batch IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?',(limit,offset))]
        return dict(items=[self.public(self.book(i)) for i in ids],total=total,limit=limit,offset=offset)
    def public(self,item):return {k:v for k,v in item.items() if k not in {'snapshot','config'}}
    def update(self,identity,**changes):
        allowed={'phase','state','chars','chapters','segments','done','failed','active_chapter','error'}
        if set(changes)-allowed:raise ValueError('不支持的长文状态字段')
        with self.store.lock,self.store.connect() as db:
            db.execute('UPDATE lf_books SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',list(changes.values())+[identity])
        return self.public(self.book(identity))
    def rows(self,table,where,args,order='no',limit=50,offset=0):
        # Identifiers are internal constants, never HTTP strings.
        if table in {'lf_chapters','lf_segments','lf_exports'}:where+=' AND deleted_batch IS NULL'
        with self.store.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+where,args).fetchone()[0]
            cursor=db.execute('SELECT * FROM '+table+' WHERE '+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',[*args,limit,offset]);names=[d[0] for d in cursor.description]
            items=[dict(zip(names,row)) for row in cursor]
        for item in items:
            if item.get('take'):item['take']=json.loads(item['take'])
        return dict(items=items,total=total,limit=limit,offset=offset)
    def chapters(self,identity,limit=50,offset=0):
        self.book(identity);return self.rows('lf_chapters','book_id=?',[identity],limit=limit,offset=offset)
    def chapter(self,identity,number):
        result=self.rows('lf_chapters','book_id=? AND no=?',[identity,number],limit=1)
        if not result['items']:raise KeyError('章节不存在')
        return result['items'][0]
    def segment(self,identity,number):
        result=self.rows('lf_segments','book_id=? AND no=?',[identity,number],limit=1)
        if not result['items']:raise KeyError('分段不存在')
        return result['items'][0]
    def exports(self,identity,limit=20,offset=0):
        self.book(identity)
        result=self.rows('lf_exports','book_id=?',[identity],order='created_at DESC',limit=limit,offset=offset)
        result['items']=[{**json.loads(r['body']),'state':r['state']} for r in result['items']];return result
    def export(self,identity):
        with self.store.connect() as db:row=db.execute('SELECT state,body FROM lf_exports WHERE id=?',(identity,)).fetchone()
        if not row:raise KeyError('长文导出不存在')
        return {**json.loads(row[1]),'state':row[0]}
    def save_export(self,item):
        with self.store.lock,self.store.connect() as db:
            db.execute('INSERT INTO lf_exports(id,book_id,state,body,created_at) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,body=excluded.body',(item['id'],item['book_id'],item['state'],json.dumps(item,ensure_ascii=False),item['created_at']))
        return item
