"""
FastAPI server: exposes the simulation over HTTP + WebSocket.

Endpoints:
  GET  /api/health            → { status, tick }
  GET  /api/state             → full init snapshot (for late joiners)
  POST /api/control/pause     → pause the tick loop
  POST /api/control/resume    → resume the tick loop
  WS   /ws                    → live stream of init + tick messages

WebSocket protocol (server → client):
  { type: "init",    tick, world, agents }
  { type: "tick",    tick, agents, events, world_resources }
  { type: "control", paused: bool }

WebSocket protocol (client → server):
  { type: "pause" }
  { type: "resume" }
"""

import asyncio
import threading
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from server.event_bus import EventBus
from simulation.engine import SimulationEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state (populated by run_server.py before uvicorn starts)
# ---------------------------------------------------------------------------
engine: Optional[SimulationEngine] = None
event_bus = EventBus()
pause_flag = threading.Event()   # set = paused, clear = running


# ---------------------------------------------------------------------------
# Lifespan: start sim thread when the server comes up
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    event_bus.set_loop(loop)

    def _run_sim():
        if engine is None:
            return
        try:
            engine.run_with_callback(
                on_tick=event_bus.emit_sync,
                pause_flag=pause_flag,
            )
        except Exception:
            logger.exception("Simulation thread crashed")

    sim_thread = threading.Thread(target=_run_sim, daemon=True, name="sim-thread")
    sim_thread.start()
    logger.info("Simulation thread started")

    yield

    # Daemon thread dies automatically with the process


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Emerge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "tick": engine.current_tick if engine else 0,
        "paused": pause_flag.is_set(),
        "agents": len(engine.agents) if engine else 0,
    }


@app.get("/api/state")
def state():
    if engine is None:
        return {"error": "Engine not initialized"}
    return engine.get_init_message()


@app.post("/api/control/pause")
def pause():
    pause_flag.set()
    event_bus.emit_sync({"type": "control", "paused": True})
    return {"paused": True}


@app.post("/api/control/resume")
def resume():
    pause_flag.clear()
    event_bus.emit_sync({"type": "control", "paused": False})
    return {"paused": False}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    # Send current world snapshot immediately
    if engine is not None:
        try:
            await ws.send_json(engine.get_init_message())
        except Exception:
            await ws.close()
            return

    queue = event_bus.subscribe()

    async def receive_loop():
        """Handle messages coming from the browser (pause/resume)."""
        try:
            async for data in ws.iter_json():
                msg_type = data.get("type")
                if msg_type == "pause":
                    pause_flag.set()
                    event_bus.emit_sync({"type": "control", "paused": True})
                elif msg_type == "resume":
                    pause_flag.clear()
                    event_bus.emit_sync({"type": "control", "paused": False})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def send_loop():
        """Forward tick/control events from the engine to this client."""
        try:
            while True:
                msg = await queue.get()
                await ws.send_json(msg)
        except Exception:
            pass

    recv_task = asyncio.create_task(receive_loop())
    send_task = asyncio.create_task(send_loop())

    _, pending = await asyncio.wait(
        [recv_task, send_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

    event_bus.unsubscribe(queue)
    logger.info("WebSocket client disconnected")
