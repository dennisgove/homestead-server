"""An example Hub module, switched off. Copy this folder to start a new page.

A module gets the Hub's look (extend "base.html"), its settings and catalog,
and its API helpers. Its own data goes in paths.state/<module>/ (backed up).
"""
from fastapi import APIRouter, Request

enabled = False                       # set True (or delete this line) in your copy
menu = {"label": "Example", "href": "/example"}
router = APIRouter()


@router.get("/example")
def example_page(request: Request):
    from ...app import page           # imported late: the app imports modules first
    return page(request, "example.html", message="Hello from a Hub module.")


@router.get("/api/example")
def example_api():
    return {"ok": True}
