import time
import numpy as np

class FakeEngine:
    """Test-only fixture. Never registered in production configuration."""
    sample_rate = 24000
    failures = 0
    def __init__(self, config):
        self.model = None
        self.calls = []
    def identity(self):
        return {"model": "test-only", "revision": "1"}
    def capabilities(self):
        return dict(tts=True, voice_design=True, cloning=True, streaming=True, languages=["zh", "en"],
                    parameters={"test_strength": {"type": "number", "default": 1.5, "min": 0, "max": 3}})
    def load(self):
        self.model = True
    def unload(self):
        self.model = None
    def synthesize(self, request):
        self.calls.append(request)
        if "FAIL" in request["text"] or type(self).failures > 0:
            type(self).failures = max(0, type(self).failures - 1)
            raise ValueError("injected engine failure")
        for _ in range(4 if request.get("streaming") else 1):
            time.sleep(.03)
            yield .15*np.sin(np.arange(6000, dtype=np.float32)*.03)

class LimitedEngine(FakeEngine):
    def capabilities(self):
        return dict(tts=True, voice_design=False, cloning=False, streaming=False, languages=["en"])
