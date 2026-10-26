"""
title: Homestead library search
author: homestead
description: Before the model answers, search the offline library (every Kiwix ZIM) and add the best passages, with their titles, so the answer is grounded in the library and cites it. Installed by homestead-webui-setup.
version: 1.0
"""
import asyncio
import json
import urllib.parse
import urllib.request

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        hub_url: str = Field(default="http://host.docker.internal:8700", description="Homestead Hub, reached from this container")
        articles: int = Field(default=3, description="Library articles to add per question")
        min_words: int = Field(default=3, description="Skip the search for very short messages (greetings)")

    def __init__(self):
        self.valves = self.Valves()

    def _context(self, question: str) -> dict:
        q = urllib.parse.urlencode({"q": question, "articles": self.valves.articles})
        with urllib.request.urlopen(f"{self.valves.hub_url.rstrip('/')}/api/library/context?{q}", timeout=60) as r:
            return json.load(r)

    async def inlet(self, body: dict, __event_emitter__=None, __user__=None) -> dict:
        msgs = body.get("messages") or []
        last = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i].get("role") == "user"), None)
        if last is None:
            return body
        content = msgs[last].get("content")
        question = content if isinstance(content, str) else " ".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        if len(question.split()) < self.valves.min_words:
            return body
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "Searching the library…", "done": False}})
        try:
            ctx = await asyncio.to_thread(self._context, question)
        except Exception as e:  # library or Hub down: answer without it
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Library search unavailable ({e})", "done": True}})
            return body
        if ctx.get("context"):
            msgs.insert(last, {"role": "system", "content": (
                "Passages from the offline library that may help answer the next question. Use them when they're "
                "relevant, cite them by number like [1], and say so if they don't cover the question. Don't invent "
                "doses or procedures that aren't in them.\n\n" + ctx["context"])})
            body["messages"] = msgs
            if __event_emitter__:
                for s in ctx.get("sources", []):
                    await __event_emitter__({"type": "citation", "data": {
                        "document": [s["title"]], "metadata": [{"source": s["url"], "name": f"[{s['n']}] {s['title']}"}],
                        "source": {"name": f"[{s['n']}] {s['title']} ({s['book']})", "url": s["url"]}}})
        if __event_emitter__:
            n = len(ctx.get("sources", []))
            await __event_emitter__({"type": "status", "data": {
                "description": f"Found {n} library article{'s' if n != 1 else ''} (searched: {ctx.get('query', '')})" if n else "Nothing relevant in the library",
                "done": True}})
        return body
