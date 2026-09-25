import json
from pathlib import Path


class Memory:
    def __init__(self, path, max_messages=12):
        self.path = Path(path)
        self.max_messages = max_messages
        self.data = {"conversation": []}
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except Exception:
            pass

    def save(self):
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add(self, role, text):
        if not text:
            return
        history = self.data.setdefault("conversation", [])
        history.append({"role": role, "content": text})
        if len(history) > 100:
            del history[:-100]
        self.save()

    def recent(self):
        return self.data.get("conversation", [])[-self.max_messages:]
