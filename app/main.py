import logging
import uuid
import asyncio
import os
import uvicorn

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from aiortc import RTCPeerConnection, RTCSessionDescription
from app.camera import VideoTransformTrack

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global set to store peer connections
pcs = set()

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # iterate over a copy to avoid modification issues during iteration
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                # If sending fails, assume disconnected
                logger.error(f"Error sending message: {e}")
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/data")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive, wait for client messages or disconnect
            await websocket.receive_text()
    except Exception:
        manager.disconnect(websocket)

@app.on_event("shutdown")
async def on_shutdown():
    # Close all peer connections on shutdown
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

@app.post("/offer")
async def offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    logger.info(f"Created for {request.client.host}")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)
        elif pc.connectionState == "closed":
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        logger.info(f"Track {track.kind} received")
        if track.kind == "video":
            # Callback to broadcast counts
            def broadcast_counts(in_count, out_count):
                import json
                data = json.dumps({"in_count": in_count, "out_count": out_count})
                # Schedule broadcast on the event loop
                asyncio.create_task(manager.broadcast(data))

            local_video = VideoTransformTrack(track, update_callback=broadcast_counts)
            pc.addTrack(local_video)
        
        @track.on("ended")
        async def on_ended():
            logger.info("Track ended")

    # Set the remote description
    await pc.setRemoteDescription(offer)

    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }

# Mount static files if they exist
# This is mainly for Phase 3 but good to have prepared
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
