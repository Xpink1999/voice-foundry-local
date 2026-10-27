"""Run an adapter in a disposable process; keep CUDA out of the API process."""
import logging
import multiprocessing
import os
import time

from .process_owner import ProcessOwner

log = logging.getLogger(__name__)


def engine_worker(connection, adapter, config):
    from .engines import resolve
    engine = None
    try:
        # The parent attaches process ownership before allowing any model imports.
        if connection.recv()[0] != 'load':
            return
        threads = str(config.get('engine_config', {}).get('cpu_threads', 4))
        for name in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            os.environ[name] = threads
        engine = resolve(adapter)(config)
        engine.load()
        connection.send(('ready', engine.sample_rate))
        while True:
            command, request = connection.recv()
            if command == 'stop':
                return
            stream = None
            try:
                stream = iter(engine.synthesize(request))
                for chunk in stream:
                    connection.send(('chunk', chunk))
                    # Backpressure: only one chunk may be in flight.
                    if connection.recv()[0] != 'next':
                        break
                connection.send(('done', None))
            except Exception as error:
                log.exception('isolated speech generation failed')
                connection.send(('error', str(error)))
            finally:
                if stream is not None and hasattr(stream, 'close'):
                    stream.close()
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        log.exception('isolated speech engine failed')
        try:
            connection.send(('error', str(error)))
        except (OSError, EOFError):
            pass
    finally:
        if engine is not None:
            engine.unload()
        connection.close()


class ProcessEngine:
    def __init__(self, adapter, config):
        from .engines import resolve
        self.adapter = adapter
        self.config = config
        # Capabilities and identity must be available without loading weights.
        self.metadata = resolve(adapter)(config)
        self.sample_rate = self.metadata.sample_rate
        self.process = None
        self.connection = None
        self.owner = None

    def identity(self):
        return self.metadata.identity()

    def capabilities(self):
        return self.metadata.capabilities()

    def readiness(self):
        check=getattr(self.metadata,'readiness',None)
        return check() if check else dict(available=True,check='adapter_not_declared')

    @property
    def pid(self):
        process = self.process
        try:
            return process.pid if process is not None and process.is_alive() else None
        except ValueError:  # A concurrent unload has already closed its process handle.
            return None

    @property
    def loaded(self):
        return self.pid is not None

    def _receive(self):
        deadline = time.monotonic() + self.config.get('engine_timeout_seconds', 7200)
        connection, process = self.connection, self.process
        while connection is not None and process is not None:
            if connection.poll(.1):
                try:
                    kind, value = connection.recv()
                except EOFError:
                    break
                if kind == 'error':
                    raise ValueError(value)
                return kind, value
            if not process.is_alive():
                break
            if time.monotonic() >= deadline:
                self.unload()
                raise TimeoutError('Speech engine timed out; its process was released.')
        raise RuntimeError('Speech engine process stopped; existing audio is preserved.')

    def load(self):
        if self.process is not None and self.process.is_alive():
            return
        self.unload()
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        process = context.Process(target=engine_worker, args=(child, self.adapter, self.config), daemon=True)
        self.connection, self.process = parent, process
        try:
            process.start()
            child.close()
            self.owner = ProcessOwner(process.pid)
            self.connection.send(('load', None))
            kind, self.sample_rate = self._receive()
            if kind != 'ready':
                raise RuntimeError('Speech engine did not finish loading.')
        except BaseException:
            child.close()
            self.unload()
            raise

    def unload(self):
        process, connection, owner = self.process, self.connection, self.owner
        self.process = self.connection = self.owner = None
        if process is not None and process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            if process.is_alive():
                raise RuntimeError('Speech engine process could not be stopped.')
            process.close()
        if connection is not None:
            connection.close()
        if owner is not None:
            owner.close()

    def interrupt(self):
        # Called before joining the producer threads; cleanup stays with their owner.
        process = self.process
        try:
            if process is not None and process.pid is not None and process.is_alive():
                process.terminate()
        except (OSError, ValueError):
            pass  # The producer may have already released this process.

    def synthesize(self, request):
        self.load()
        completed = False
        try:
            self.connection.send(('generate', request))
            while True:
                kind, value = self._receive()
                if kind == 'done':
                    completed = True
                    return
                if kind != 'chunk':
                    raise RuntimeError('Invalid speech engine response.')
                yield value
                self.connection.send(('next', None))
        finally:
            # Cancelled/failed iterators must never leave a GPU worker waiting for an ACK.
            if not completed:
                self.unload()
