import os
import threading
import time
from pathlib import Path
import uvicorn
from .api import create_app
from .config import load_config

def main():
    cfg = load_config()
    app = create_app(cfg)
    server = uvicorn.Server(uvicorn.Config(app, host=cfg["host"], port=cfg["port"], log_level="info", timeout_graceful_shutdown=45))
    def monitor():
        while not server.should_exit:
            if getattr(app.state, "stop_requested", False):
                time.sleep(0.4)
                server.should_exit = True
                return
            time.sleep(0.3)
    threading.Thread(target=monitor, daemon=True).start()
    server.run()

if __name__ == "__main__":
    main()
