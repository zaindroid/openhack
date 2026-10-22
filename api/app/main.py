"""FloodSense EU API skeleton.

Only ``GET /health`` is implemented. Runs, SSE, approval, cache, and rate
limits are later increments. See docs/GAMEPLAN.md.
"""

from fastapi import FastAPI

app = FastAPI(title="FloodSense EU", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "floodsense-api"}
