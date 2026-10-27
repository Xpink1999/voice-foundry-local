"""Recoverable asset deletion. Files and frozen provenance remain intact."""
import json
from collections import Counter
from .store import now,uid

KINDS={'projects':'项目','voices':'人物音色','voice_versions':'音色历史版本','references':'参考片段','recordings':'参考录音','jobs':'生成任务','results':'试听结果','exports':'导出记录','audio_processing':'音频处理','reference_comparisons':'参考对比','longform_books':'长文作品','longform_chapters':'长文章节','longform_segments':'长文分段','longform_exports':'长文导出'}
KINDS['export_tasks']='导出任务'
LF={'longform_books':'lf_books','longform_chapters':'lf_chapters','longform_segments':'lf_segments','longform_exports':'lf_exports'}
ACTIVE={'queued','running','generating','cancel_requested','uploading','indexing'}
class Assets:
    def __init__(self,platform):
        self.platform=platform;self.store=platform.store
        with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS asset_trash(kind TEXT,id TEXT,batch_id TEXT,deleted_at TEXT,name TEXT,PRIMARY KEY(kind,id))')
    def validate(self,kind):
        if kind not in KINDS:raise ValueError('不支持此资产类别')
    def row(self,db,kind,identity):
        self.validate(kind)
        if kind not in LF:
            row=db.execute('SELECT body FROM entities WHERE kind=? AND id=?',(kind,identity)).fetchone()
            if not row:raise KeyError('资产不存在')
            return json.loads(row[0])
        table=LF[kind];where='id=?';args=[identity]
        if kind in {'longform_chapters','longform_segments'}:
            try:book,number=identity.rsplit(':',1);number=int(number)
            except ValueError:raise ValueError('章节或分段标识不正确')
            where='book_id=? AND no=?';args=[book,number]
        cursor=db.execute('SELECT * FROM '+table+' WHERE '+where,args);row=cursor.fetchone()
        if not row:raise KeyError('长文资产不存在')
        value=dict(zip([d[0] for d in cursor.description],row))
        if 'body' in value:value={**json.loads(value.pop('body')),**value}
        return dict(value,id=identity)
    def summary(self,kind,row):
        title=row.get('name') or row.get('title') or row.get('original_name') or row.get('book_title') or row.get('source_label') or (f'第 {row.get("no")} 段' if kind=='longform_segments' else row['id'])
        return dict(kind=kind,id=row['id'],name=title,status=row.get('status') or row.get('state') or row.get('review'),created_at=row.get('created_at'),deleted_at=row.get('deleted_at'),book_id=row.get('book_id'))
    def page(self,kind,limit=50,offset=0,deleted=False,book_id=None):
        self.validate(kind)
        with self.store.connect() as db:
            if deleted:
                total=db.execute('SELECT COUNT(*) FROM asset_trash WHERE kind=?',(kind,)).fetchone()[0]
                rows=db.execute('SELECT id,batch_id,deleted_at,name FROM asset_trash WHERE kind=? ORDER BY deleted_at DESC LIMIT ? OFFSET ?',(kind,limit,offset)).fetchall()
                items=[dict(kind=kind,id=r[0],batch_id=r[1],deleted_at=r[2],name=r[3]) for r in rows]
            else:
                if kind not in LF:
                    where="kind=? AND COALESCE(json_extract(body,'$.deleted_at'),'')=''";args=[kind];table='entities';idcol='id';order='rowid DESC'
                else:
                    table=LF[kind];where='deleted_batch IS NULL';args=[];idcol='id';order='rowid DESC'
                    if kind in {'longform_chapters','longform_segments'}:
                        if not book_id:raise ValueError('请先选择长文作品')
                        where+=' AND book_id=?';args.append(book_id);idcol="book_id||':'||no";order='no'
                total=db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+where,args).fetchone()[0]
                ids=[r[0] for r in db.execute('SELECT '+idcol+' FROM '+table+' WHERE '+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',[*args,limit,offset])]
                items=[self.summary(kind,self.row(db,kind,i)) for i in ids]
        return dict(items=items,total=total,limit=limit,offset=offset)
    def _collect(self,db,items,cascade):
        chosen={};queue=[(i.kind,i.id) if hasattr(i,'kind') else (i['kind'],i['id']) for i in items]
        while queue:
            kind,identity=queue.pop()
            if (kind,identity) in chosen:continue
            row=self.row(db,kind,identity)
            if row.get('deleted_at') or row.get('deleted_batch'):continue
            chosen[kind,identity]=row
            if not cascade:continue
            def related(child,field,value):
                for r in db.execute("SELECT id FROM entities WHERE kind=? AND COALESCE(json_extract(body,'$.deleted_at'),'')='' AND json_extract(body,?)=?",(child,'$.'+field,value)):queue.append((child,r[0]))
            if kind=='jobs':related('results','job_id',identity)
            elif kind=='voices':related('voice_versions','voice_id',identity)
            elif kind=='projects':
                for child in ['voices','jobs','results']:related(child,'project_id',identity)
                for r in db.execute("SELECT id FROM lf_books WHERE deleted_batch IS NULL AND json_extract(body,'$.snapshot.project_id')=?",(identity,)):queue.append(('longform_books',r[0]))
            elif kind=='recordings':
                related('recordings','parent_recording_id',identity);related('references','recording_id',identity);related('audio_processing','recording_id',identity)
            elif kind=='audio_processing':
                for child in row.get('child_recording_ids',[]):queue.append(('recordings',child))
                related('references','processing_id',identity)
                related('audio_processing','source_processing_id',identity)
        return chosen
    def _blocked(self,db,chosen):
        errors=[]
        for (kind,identity),row in chosen.items():
            if kind=='results':
                busy=db.execute("SELECT 1 FROM entities e,json_each(e.body,'$.request.result_ids') j WHERE e.kind='export_tasks' AND json_extract(e.body,'$.status') IN ('queued','running','cancel_requested') AND j.value=? LIMIT 1",(identity,)).fetchone()
                if busy:errors.append('所选音频正在导出，请先取消或等待导出结束')
            state=row.get('status') or row.get('state')
            if state in ACTIVE and kind not in {'voices','voice_versions'}:errors.append(self.summary(kind,row)['name']+'：请先停止或等待当前任务结束')
            if kind=='recordings' and row.get('smart_reference',{}).get('status') in {'analyzing','processing','analyzing_outputs'}:errors.append('该录音正在自动整理，请先停止')
            if kind in LF:
                bookid=row.get('book_id') or (identity if kind=='longform_books' else None)
                if bookid:
                    book=self.row(db,'longform_books',bookid)
                    busy=db.execute("SELECT 1 FROM lf_segments WHERE book_id=? AND status='running' LIMIT 1",(bookid,)).fetchone()
                    export=db.execute("SELECT 1 FROM lf_exports WHERE book_id=? AND state IN ('queued','running','cancel_requested') LIMIT 1",(bookid,)).fetchone()
                    if book['state']=='running' or book['phase'] in ACTIVE or busy or export:errors.append('长文作品正在生成、导入或导出，请先暂停或等待结束')
            if kind=='references':
                for voice in self.store.list('voices'):
                    if ('voices',voice['id']) not in chosen and identity in [voice.get('reference_id'),*voice.get('reference_ids',[])]:errors.append(f'参考仍被人物「{voice["name"]}」使用，请先解除绑定或同时删除人物')
            if kind=='voice_versions':
                voice=self.row(db,'voices',row['voice_id'])
                if voice['version']==row['version'] and ('voices',voice['id']) not in chosen:errors.append('当前音色版本不能单独删除，请编辑人物或删除整个人物')
        return list(dict.fromkeys(errors))
    def preview(self,items,cascade=True):
        with self.store.lock,self.store.connect() as db:
            chosen=self._collect(db,items,cascade);blocked=self._blocked(db,chosen)
        return dict(total=len(chosen),counts=dict(Counter(k for k,i in chosen)),items=[self.summary(k,r) for (k,i),r in list(chosen.items())[:50]],blocked=blocked,note='移入回收站，可恢复；原音频、模型、原文和追踪记录不物理删除。长文章节删除会排除其分段，重新审核后再正式导出。')
    def _recount(self,db,bookid,changed):
        for no, in db.execute('SELECT no FROM lf_chapters WHERE book_id=? AND deleted_batch IS NULL',(bookid,)).fetchall():
            total,done,failed=db.execute("SELECT COUNT(*),COALESCE(SUM(status='succeeded'),0),COALESCE(SUM(status='failed'),0) FROM lf_segments WHERE book_id=? AND chapter_no=? AND deleted_batch IS NULL",(bookid,no)).fetchone()
            db.execute('UPDATE lf_chapters SET segments=?,done=?,failed=?'+(",revision=revision+1,review='pending'" if no in changed else '')+' WHERE book_id=? AND no=?',(total,done,failed,bookid,no))
        ch,total,done,failed=db.execute('SELECT COUNT(*),COALESCE(SUM(segments),0),COALESCE(SUM(done),0),COALESCE(SUM(failed),0) FROM lf_chapters WHERE book_id=? AND deleted_batch IS NULL',(bookid,)).fetchone()
        db.execute("UPDATE lf_books SET chapters=?,segments=?,done=?,failed=?,state='paused',active_chapter=NULL WHERE id=?",(ch,total,done,failed,bookid))
    def delete(self,items,cascade=True):
        with self.store.lock,self.store.connect() as db:
            chosen=self._collect(db,items,cascade);blocked=self._blocked(db,chosen)
            if blocked:raise ValueError('；'.join(blocked[:10]))
            batch=uid();stamp=now();books={}
            for (kind,identity),row in chosen.items():
                name=self.summary(kind,row)['name'];db.execute('INSERT INTO asset_trash VALUES (?,?,?,?,?)',(kind,identity,batch,stamp,name))
                if kind not in LF:
                    row.update(deleted_at=stamp,deleted_batch=batch);db.execute('UPDATE entities SET body=? WHERE kind=? AND id=?',(json.dumps(row,ensure_ascii=False),kind,identity))
                elif kind in {'longform_books','longform_exports'}:db.execute('UPDATE '+LF[kind]+' SET deleted_batch=? WHERE id=?',(batch,identity))
                else:
                    book,no=identity.rsplit(':',1);db.execute('UPDATE '+LF[kind]+' SET deleted_batch=? WHERE book_id=? AND no=?',(batch,book,int(no)));books.setdefault(book,set()).add(int(no) if kind=='longform_chapters' else row['chapter_no'])
                    if kind=='longform_chapters':db.execute('UPDATE lf_segments SET deleted_batch=? WHERE book_id=? AND chapter_no=? AND deleted_batch IS NULL',(batch,book,int(no)))
            for book,changed in books.items():self._recount(db,book,changed)
        return dict(batch_id=batch,deleted=len(chosen),counts=dict(Counter(k for k,i in chosen)),recoverable=True)
    def restore(self,items):
        with self.store.lock,self.store.connect() as db:
            selected=[];books={}
            for item in items:
                kind,identity=(item.kind,item.id) if hasattr(item,'kind') else (item['kind'],item['id']);self.validate(kind)
                row=db.execute('SELECT batch_id FROM asset_trash WHERE kind=? AND id=?',(kind,identity)).fetchone()
                if row:selected.append((kind,identity,row[0]))
            selected.sort(key=lambda r:0 if r[0]=='longform_books' else 1 if r[0]=='longform_chapters' else 2)
            # Restore a selected entry; restore-batch is available for cascade groups.
            for kind,identity,batch in selected:
                row=self.row(db,kind,identity)
                if kind not in LF:
                    row.pop('deleted_at',None);row.pop('deleted_batch',None);db.execute('UPDATE entities SET body=? WHERE kind=? AND id=?',(json.dumps(row,ensure_ascii=False),kind,identity))
                elif kind in {'longform_books','longform_exports'}:db.execute('UPDATE '+LF[kind]+' SET deleted_batch=NULL WHERE id=?',(identity,))
                else:
                    book,no=identity.rsplit(':',1)
                    parent=self.row(db,'longform_books',book)
                    if parent.get('deleted_batch'):raise ValueError('请先恢复所属长文作品')
                    if parent['state']=='running' or db.execute("SELECT 1 FROM lf_segments WHERE book_id=? AND status='running' LIMIT 1",(book,)).fetchone() or db.execute("SELECT 1 FROM lf_exports WHERE book_id=? AND state IN ('queued','running','cancel_requested') LIMIT 1",(book,)).fetchone():raise ValueError('请先暂停生成或等待导出结束，再恢复章节和分段')
                    if kind=='longform_segments' and self.row(db,'longform_chapters',book+':'+str(row['chapter_no'])).get('deleted_batch'):raise ValueError('请先恢复所属章节')
                    db.execute('UPDATE '+LF[kind]+' SET deleted_batch=NULL WHERE book_id=? AND no=?',(book,int(no)));books.setdefault(book,set()).add(int(no) if kind=='longform_chapters' else row['chapter_no'])
                    if kind=='longform_chapters':db.execute('UPDATE lf_segments SET deleted_batch=NULL WHERE book_id=? AND chapter_no=? AND deleted_batch=?',(book,int(no),batch))
                db.execute('DELETE FROM asset_trash WHERE kind=? AND id=?',(kind,identity))
            for book,changed in books.items():self._recount(db,book,changed)
        return dict(restored=len(selected))
    def restore_batch(self,batch):
        with self.store.connect() as db:items=[dict(kind=k,id=i) for k,i in db.execute('SELECT kind,id FROM asset_trash WHERE batch_id=?',(batch,))]
        # Parent books precede their chapter/segment entries.
        items.sort(key=lambda x:0 if x['kind']=='longform_books' else 1)
        return self.restore(items)
