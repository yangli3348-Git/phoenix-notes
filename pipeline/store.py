"""
数据管理 — 状态持久化 + popup_data.json 读写
"""

import json, os

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class State:
    def __init__(self, path):
        self.path = path
        self.data = load_json(path, {"last_id": -1, "processed": {}})

    def save(self):
        save_json(self.path, self.data)

    @property
    def last_id(self):
        return self.data["last_id"]

    @last_id.setter
    def last_id(self, v):
        self.data["last_id"] = v

    @property
    def processed(self):
        return self.data.get("processed", {})

    def mark_processed(self, key):
        self.data["processed"][key] = True

class PopupStore:
    MAX = 20

    def __init__(self, path):
        self.path = path

    def load(self):
        return load_json(self.path, [])

    def save(self, data):
        save_json(self.path, data[-self.MAX:])

    def append(self, item):
        data = self.load()
        data.append(item)
        self.save(data)
        return data
