from __future__ import annotations

import threading
import uvicorn
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --------------- Config ---------------
API_PORT = 8000
PANEL_PORT = 8080

# --------------- Shared storage ---------------
entries: list[dict] = []

# --------------- Models ---------------

class LocationData(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    accuracy: float | None = None
    altitude: float | None = None
    altitude_accuracy: float | None = None
    heading: float | None = None
    speed: float | None = None

class DeviceInfo(BaseModel):
    user_agent: str | None = None
    platform: str | None = None
    language: str | None = None
    languages: list[str] = []
    screen_width: int | None = None
    screen_height: int | None = None
    device_pixel_ratio: float | None = None
    timezone: str | None = None
    online: bool | None = None
    cookie_enabled: bool | None = None
    hardware_concurrency: int | None = None
    max_touch_points: int | None = None

class CollectPayload(BaseModel):
    ip: str | None = None
    location: LocationData | None = None
    device_info: DeviceInfo | None = None
    timestamp: str | None = None

# --------------- API app (port 8000) ---------------
api_app = FastAPI()

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend HTML at the root of the API app
api_app.mount("/static", StaticFiles(directory="../frontend"), name="static")


@api_app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("../frontend/index.html") as f:
        return HTMLResponse(f.read())


@api_app.post("/api/collect")
async def collect(payload: CollectPayload, request: Request):
    entry = payload.model_dump()
    # Also capture the server-side IP as a fallback
    entry["server_seen_ip"] = request.client.host if request.client else None
    entry["received_at"] = datetime.utcnow().isoformat()
    entries.append(entry)
    return {"status": "ok"}


# --------------- Panel app (port 8080) ---------------
panel_app = FastAPI()


def _esc(val: str | None) -> str:
    if val is None:
        return ""
    return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@panel_app.get("/", response_class=HTMLResponse)
async def panel():
    rows = ""
    for i, e in enumerate(reversed(entries), 1):
        loc = e.get("location") or {}
        dev = e.get("device_info") or {}
        lat = loc.get("latitude", "—")
        lon = loc.get("longitude", "—")
        acc = loc.get("accuracy", "—")
        maps_link = ""
        if loc.get("latitude") is not None and loc.get("longitude") is not None:
            maps_link = f'<a href="https://www.google.com/maps?q={lat},{lon}" target="_blank">Open Map</a>'

        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{_esc(e.get("ip"))}<br><small>server: {_esc(e.get("server_seen_ip"))}</small></td>
            <td>{lat}, {lon}<br><small>accuracy: {acc}m</small><br>{maps_link}</td>
            <td title="{_esc(dev.get("user_agent"))}">
                <strong>Platform:</strong> {_esc(dev.get("platform"))}<br>
                <strong>Screen:</strong> {dev.get("screen_width")}x{dev.get("screen_height")} @{dev.get("device_pixel_ratio")}x<br>
                <strong>Language:</strong> {_esc(dev.get("language"))}<br>
                <strong>Timezone:</strong> {_esc(dev.get("timezone"))}<br>
                <strong>Touch:</strong> {dev.get("max_touch_points")} pts<br>
                <strong>Cores:</strong> {dev.get("hardware_concurrency")}<br>
                <small>{_esc(dev.get("user_agent"))}</small>
            </td>
            <td>{_esc(e.get("timestamp"))}<br><small>rcvd: {_esc(e.get("received_at"))}</small></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visitor Panel</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
        h1 {{ text-align: center; margin-bottom: 20px; color: #00d4ff; }}
        .count {{ text-align: center; margin-bottom: 16px; color: #888; }}
        table {{ width: 100%; border-collapse: collapse; background: #16213e; border-radius: 8px; overflow: hidden; }}
        th {{ background: #0f3460; padding: 12px 10px; text-align: left; color: #00d4ff; font-size: 0.85em; text-transform: uppercase; }}
        td {{ padding: 10px; border-bottom: 1px solid #1a1a2e; vertical-align: top; font-size: 0.9em; word-break: break-word; }}
        tr:hover td {{ background: #1a2744; }}
        a {{ color: #00d4ff; }}
        small {{ color: #888; }}
        .refresh {{ text-align: center; margin-top: 16px; }}
        .refresh a {{ color: #00d4ff; text-decoration: none; padding: 8px 20px; border: 1px solid #00d4ff; border-radius: 4px; }}
        .refresh a:hover {{ background: #00d4ff; color: #1a1a2e; }}
    </style>
</head>
<body>
    <h1>Visitor Panel</h1>
    <p class="count">{len(entries)} visitor(s) collected</p>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>IP</th>
                <th>Location</th>
                <th>Device Info</th>
                <th>Timestamp</th>
            </tr>
        </thead>
        <tbody>
            {rows if rows else '<tr><td colspan="5" style="text-align:center;padding:40px;">No visitors yet.</td></tr>'}
        </tbody>
    </table>
    <div class="refresh"><a href="/">Refresh</a></div>
</body>
</html>"""
    return HTMLResponse(html)


# --------------- Run both servers ---------------
def run_panel():
    uvicorn.run(panel_app, host="0.0.0.0", port=PANEL_PORT, log_level="info")


if __name__ == "__main__":
    panel_thread = threading.Thread(target=run_panel, daemon=True)
    panel_thread.start()
    print(f"\n  Frontend + API : http://localhost:{API_PORT}")
    print(f"  Panel          : http://localhost:{PANEL_PORT}\n")
    uvicorn.run(api_app, host="0.0.0.0", port=API_PORT, log_level="info")
