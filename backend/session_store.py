from typing import Optional


class SessionStore:
    def __init__(self):
        self._store: dict = {}

    def get_or_create(self, session_id: str) -> dict:
        if session_id not in self._store:
            self._store[session_id] = {"history": [], "sources": []}
        return self._store[session_id]

    def update(self, session_id: str, query: str, report: str, sources: list[dict]):
        session = self.get_or_create(session_id)
        session["history"].append({"query": query, "report": report})
        session["sources"] = sources

    def get_sources(self, session_id: str) -> list[dict]:
        return self._store.get(session_id, {}).get("sources", [])

    def get_history(self, session_id: str) -> list[dict]:
        return self._store.get(session_id, {}).get("history", [])

    def delete(self, session_id: str):
        self._store.pop(session_id, None)


session_store = SessionStore()
