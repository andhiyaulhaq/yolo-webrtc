import logging
import uuid
import asyncio
import os
import time
import uvicorn
from dotenv import load_dotenv
from app.notifier import Notifier
from app.schema import TokenRequest
from firebase_admin import messaging

load_dotenv()

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from aiortc import RTCPeerConnection, RTCSessionDescription
from app.camera import VideoTransformTrack

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Notifier
notifier = Notifier()

# Initialize Database
from app.database import init_db
init_db()

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

@app.post("/subscribe")
async def subscribe_to_topic(request: TokenRequest):
    """
    Subscribes a client FCM token to the 'alerts' topic.
    """
    topic = "alerts"
    tokens = [request.token]
    
    if notifier.mock_mode:
        logger.info(f"MOCK SUBSCRIPTION: Added {request.token[:10]}... to topic '{topic}'")
        return {"message": "Success (Mock)", "count": 1}

    try:
        response = messaging.subscribe_to_topic(tokens, topic)
        logger.info(f"Successfully subscribed to topic: {response.success_count} success, {response.failure_count} failure")
        return {"message": "Success", "count": response.success_count}
    except Exception as e:
        logger.error(f"Error subscribing to topic: {e}")
        return {"message": f"Error: {str(e)}", "count": 0}

@app.post("/unsubscribe")
async def unsubscribe_from_topic(request: TokenRequest):
    """
    Unsubscribes a client FCM token from the 'alerts' topic.
    """
    topic = "alerts"
    tokens = [request.token]
    
    if notifier.mock_mode:
        logger.info(f"MOCK UNSUBSCRIPTION: Removed {request.token[:10]}... from topic '{topic}'")
        return {"message": "Success (Mock)", "count": 1}

    try:
        response = messaging.unsubscribe_from_topic(tokens, topic)
        logger.info(f"Successfully unsubscribed from topic: {response.success_count} success, {response.failure_count} failure")
        return {"message": "Success", "count": response.success_count}
    except Exception as e:
        logger.error(f"Error unsubscribing from topic: {e}")
        return {"message": f"Error: {str(e)}", "count": 0}

@app.on_event("shutdown")
async def on_shutdown():
    # Close all peer connections on shutdown
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

@app.get("/models")
async def get_models():
    """
    Returns a list of available YOLO models in the 'models/' directory.
    """
    models_dir = "models"
    if not os.path.exists(models_dir):
        return []
    
    # List .pt files
    models = [f for f in os.listdir(models_dir) if f.endswith(".pt")]
    
    # Return full paths or just filenames? 
    # Frontend can display filenames, we reconstruct path here or send full path.
    # Let's send filenames.
    return {"models": models, "current": os.getenv("YOLO_MODEL", "models/yolov8n.pt")}

@app.post("/offer")
async def offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    # Get selected model from params, default to env var or hardcoded default
    selected_model = params.get("model")
    if selected_model:
        # Sanitize potentially (prevent directory traversal)
        selected_model = os.path.basename(selected_model) 
        model_path = os.path.join("models", selected_model)
    else:
        model_path = os.getenv("YOLO_MODEL", "models/yolov8n.pt")

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
            # State for alert cooldown (mutable to be accessible in callback)
            alert_state = {"last_alert_time": 0}
            
            # Callback to broadcast counts
            def broadcast_counts(in_count, out_count):
                import json
                data = json.dumps({"in_count": in_count, "out_count": out_count})
                # Schedule broadcast on the event loop
                asyncio.create_task(manager.broadcast(data))

                # Check for alerts
                try:
                    from app.database import log_alert
                    
                    threshold = int(os.getenv("MAX_PEOPLE_THRESHOLD", 10))
                    
                    # Alert Logic:
                    # 1. Count must exceed threshold
                    # 2. Cooldown of 60 seconds must have passed since last alert
                    if in_count > threshold:
                        current_time = time.time()
                        if (current_time - alert_state["last_alert_time"]) > 60:
                            # Log alert to DB
                            asyncio.get_event_loop().run_in_executor(None, log_alert, in_count, threshold)
                            
                            # Run blocking FCM call in executor
                            loop = asyncio.get_event_loop()
                            loop.run_in_executor(None, notifier.send_alert, in_count, threshold)
                            
                            # Update last alert time
                            alert_state["last_alert_time"] = current_time
                            logger.info(f"Alert triggered! Count: {in_count}, Threshold: {threshold}")
                            
                except Exception as e:
                    logger.error(f"Error triggering alert: {e}")

            local_video = VideoTransformTrack(track, update_callback=broadcast_counts, model_path=model_path)
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
