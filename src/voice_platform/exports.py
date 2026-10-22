from pathlib import Path

class StandardExport:
    def folder(self, result):
        return Path("audio")

class GameAudioExport:
    def folder(self, result):
        return Path("assets/audio/voices") / (result["voice_snapshot"]["id"] if result.get("voice_snapshot") else "narrator")

class MediaExport:
    def folder(self, result):
        return Path("dubbing") / (result.get("project_id") or "independent")
