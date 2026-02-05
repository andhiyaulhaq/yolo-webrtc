# People Counter AI Pipeline

This project is a sophisticated **IoT + AI pipeline** that bridges low-latency video streaming with intelligent edge analytics. It is designed for **asynchrony** and **ease of integration**, transitioning from a C++ mindset to Python for prototyping.

## 🏗️ 1. Project Objective

To build a real-time system that detects and counts people crossing a boundary in a video feed. The system must provide a live visual stream, a data dashboard for counts, and mobile alerts for specific triggers.

## 🛠️ 2. The Tech Stack

You are utilizing four distinct communication and processing layers:

*   **AI Engine:** **Python + PyTorch + YOLOv8**. This handles the "brain" of the project (detection and tracking).
*   **Video Streaming:** **WebRTC (`aiortc`)**. Provides the < 500ms latency needed for "real-time" visual monitoring.
*   **Data Channel:** **WebSockets (FastAPI)**. Pushes the raw integer counts (In/Out) to the web dashboard instantly.
*   **Alerting:** **FCM (Firebase Cloud Messaging)**. Handles "out-of-band" notifications to mobile devices when thresholds are met.

## 📐 3. System Architecture

The flow is designed to handle "Heavy" data (Video) and "Light" data (Counts) separately to ensure performance.

1.  **Ingestion:** The server receives a video stream (via WebRTC from a browser or RTSP from an IP camera).
2.  **Processing:** Inside the `aiortc` loop, each frame is passed to **YOLO**.
    *   **Tracking:** Assigns a unique ID to each person.
    *   **Counting:** Detects when a specific ID's centroid crosses a pre-defined line.
3.  **Distribution:**
    *   The **annotated frame** (with boxes and lines) is sent back via **WebRTC**.
    *   The **numerical data** is pushed via **WebSockets**.
    *   **Logic Check:** If `count > limit`, a request is sent to **FCM**.

## 📁 4. Project Structure

To keep the prototype organized, the structure separates the **AI logic**, **WebRTC streaming**, and **messaging services**.

```text
people-counter-ai/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entry point & Signaling server
│   ├── camera.py            # WebRTC MediaStreamTrack & YOLO logic
│   ├── counter_logic.py     # Custom YOLO tracking & line-crossing rules
│   └── notifier.py          # FCM (Firebase) alert functions
├── models/
│   └── yolov8n.pt           # Your PyTorch model file
├── static/
│   ├── index.html           # Dashboard UI
│   ├── js/
│   │   └── main.js          # WebRTC & WebSocket client-side logic
│   └── css/
│       └── style.css
├── .env                     # API Keys, FCM Config, & Camera URLs
├── requirements.txt         # Project dependencies
└── firebase_creds.json      # Service account key for FCM
```

### 📄 Essential Files Breakdown

#### `requirements.txt`
Core libraries needed:
*   `fastapi`, `uvicorn`
*   `aiortc`, `av`
*   `ultralytics`, `opencv-python`
*   `firebase-admin`, `python-dotenv`

#### `app/camera.py`
The "heart" of the project. Inherits from `aiortc.VideoStreamTrack`.
1.  Receives a frame.
2.  Passes it to `model.track()`.
3.  Draws counting lines.
4.  Returns the annotated frame.

#### `app/main.py`
Handles **Signaling** and **WebSockets**.
*   **POST `/offer`**: Receives WebRTC offer.
*   **WS `/ws/data`**: Sends `in_count` and `out_count`.

#### `app/notifier.py`
Utility script using `firebase-admin` to trigger push notifications when thresholds are met.

## 📋 5. Development Roadmap

### **Phase 1: The AI Core**
*   Set up Python environment with `ultralytics` and `opencv-python`.
*   Implement `ObjectCounter` logic.
*   Fine-tune "Virtual Line" coordinates.

### **Phase 2: The Streaming Server**
*   Build **FastAPI** server.
*   Integrate `aiortc` for signaling.
*   Create `VideoTransformTrack` to wrap YOLO logic.

### **Phase 3: Real-time UI & Alerts**
*   Add **WebSocket** endpoint for broadcasting counts.
*   Create HTML/JS dashboard.
*   Initialize `firebase-admin` for notifications.

## 💡 Key Design Decisions

*   **Model Choice:** **YOLOv8n** (Nano) for fast CPU-based prototyping.
*   **Concurrency:** Python's `asyncio` to keep the server responsive during heavy processing.
*   **Tracking:** Use `persist=True` in model calls to maintain IDs across frames.

> **Note:** For WebSockets, ensure a global variable or "Manager" class is used to share count values between the AI thread and the WebSocket thread.
