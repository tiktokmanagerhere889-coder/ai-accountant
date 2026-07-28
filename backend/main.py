from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="AI Accountant", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}
