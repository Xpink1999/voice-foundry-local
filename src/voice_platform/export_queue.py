"""Durable ordinary export queue; interrupted work is explicit, never re-submitted on refresh."""
import threading
from .schemas import ExportInput
from .store import now,uid


class ExportQueue:
    def __init__(self,platform):
        self.platform=platform;self.store=platform.store;self.thread=None
        self.wake=threading.Event();self.stop_event=threading.Event();self.current=None

    def start(self):
        for item in self.store.by_status('export_tasks',['running','cancel_requested']):
            if item['status'] in {'running','cancel_requested'}:
                self.store.update('export_tasks',item['id'],status='failed',error='服务中断，请显式重试导出；原音频保留')
        self.stop_event.clear();self.thread=threading.Thread(target=self.work,name='export-worker',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set();self.wake.set()
        if self.current:self.current.set()
        if self.thread:self.thread.join(timeout=10)

    def submit(self,request,key=None):
        body=request.model_dump()
        with self.store.lock:
            if self.platform.shutdown.is_set():raise ValueError('服务正在停止')
            if key:
                if len(key)>200:raise ValueError('幂等键过长')
                with self.store.connect() as db:
                    row=db.execute("SELECT body FROM entities WHERE kind='export_tasks' AND json_extract(body,'$.idempotency_key')=?",(key,)).fetchone()
                if row:
                    import json
                    item=json.loads(row[0])
                    if item['request']!=body:raise ValueError('同一幂等键已用于不同导出内容')
                    if item.get('deleted_at'):raise ValueError('导出任务已在回收站，请先恢复')
                    return item
            if self.store.by_status('export_tasks',['queued','running','cancel_requested'],count=True)>=self.platform.config.get('max_pending_exports',10):
                raise ValueError('导出队列已满，请稍后重试')
            self.platform.validate_export(request)
            item=dict(id=uid(),status='queued',request=body,idempotency_key=key,created_at=now(),progress=0,message='等待导出',error=None)
            self.store.save('export_tasks',item);self.wake.set();return item

    def cancel(self,identity):
        with self.store.lock:
            item=self.store.get('export_tasks',identity)
            if item['status'] in {'queued','running'}:
                status='cancelled' if item['status']=='queued' else 'cancel_requested'
                item=self.store.update('export_tasks',identity,status=status)
                if status=='cancel_requested' and self.current:self.current.set()
            return item

    def work(self):
        while not self.stop_event.is_set():
            with self.store.lock:
                queued=self.store.by_status('export_tasks',['queued'],limit=1)
                item=queued[0] if queued else None
                if item:
                    self.current=threading.Event()
                    self.store.update('export_tasks',item['id'],status='running',message='正在导出',started_at=now())
            if not item:self.wake.wait(.7);self.wake.clear();continue
            try:
                package=self.platform.export(ExportInput(**item['request']),stop_event=self.current,
                    progress=lambda n:self.store.update('export_tasks',item['id'],progress=n))
                self.store.update('export_tasks',item['id'],status='succeeded',progress=100,export_id=package['id'],message='导出包已准备好',finished_at=now())
            except Exception as error:
                self.store.update('export_tasks',item['id'],status='cancelled' if isinstance(error,InterruptedError) else 'failed',error=str(error),finished_at=now())
            finally:self.current=None
