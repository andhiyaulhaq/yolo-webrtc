# YOLO WebRTC Object Counter

A real-time object detection and counting application that processes video streams from a client device using YOLOv8 (Ultralytics) and WebRTC. The system counts people entering/exiting a defined zone and provides real-time updates via a Web UI and WebSocket.

## 🌟 Features

*   **Real-time Inference**: Uses YOLOv8 for high-performance object detection.
*   **WebRTC Integration**: Low-latency video streaming between client (browser) and server.
*   **Bi-directional Counting**: Counts objects crossing a virtual line (In/Out).
*   **Live Updates**: WebSocket updates for count statistics.
*   **Push Notifications**: Firebase Cloud Messaging integration for threshold-based alerts.
*   **Model Selection**: Dynamically switch between different YOLO models.
*   **Responsive UI**: Modern web interface with real-time stats and controls.

## 🏗 Architecture

![Architecture Diagram Placeholder](docs/architecture_diagram.png)
*(Placeholder: Add an architecture diagram showing Client <-> WebRTC <-> Server <-> YOLO Model)*

### Backend
*   **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Async Python framework)
*   **WebRTC**: `aiortc` for handling media streams.
*   **YOLO Implementation**: [Ultralytics YOLOv8](https://docs.ultralytics.com/) (`ultralytics` package).
*   **Database**: SQLite for persistent storage of counts and alert logs.
*   **Notifications**: Firebase Admin SDK.

### Frontend
*   **Tech Stack**: Vanilla HTML/JS/CSS.
*   **Connection**:
    *   **WebRTC**: Establishes a peer-to-peer connection for sending the camera stream to the server and receiving the annotated stream back.
    *   **WebSocket**: Connects to `ws://{host}/ws/data` to receive real-time updates on `in_count` and `out_count`.
*   **Rendering**: The server processes video frames, draws bounding boxes/counters, and streams the *annotated video* back to the client via WebRTC. The client simply displays this video stream.

## 🚀 Installation & Setup

### Prerequisites
*   Python 3.9+
*   Webcam or video source

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/yolo-webrtc.git
cd yolo-webrtc
```

### 2. Create a Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration
### 4. Configuration

#### Environment Variables
Create a `.env` file in the root directory:
```env
# Example .env configuration
YOLO_MODEL=models/yolov8n.pt
MAX_PEOPLE_THRESHOLD=10
FIREBASE_CREDENTIALS=firebase_creds.json
```

#### Firebase Setup (Manual Step)
To enable push notifications, you must manually provide Firebase credentials.

**Backend (Service Account):**
1.  Go to the Firebase Console -> Project Settings -> Service accounts.
2.  Generate a new private key.
3.  Save the JSON file as `firebase_creds.json` in the root directory (or update `FIREBASE_CREDENTIALS` in `.env` to point to it).

**Frontend (Client Config):**
1.  Go to the Firebase Console -> Project Settings -> General -> Your apps.
2.  Copy the `firebaseConfig` object.
3.  Go to Project Settings -> Cloud Messaging -> Web configuration to generate a **key pair** (VAPID Key).
4.  Create or update `static/js/config.js` with your specific details:
    ```javascript
    const firebaseConfig = {
        apiKey: "YOUR_API_KEY",
        authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
        projectId: "YOUR_PROJECT_ID",
        storageBucket: "YOUR_PROJECT_ID.appspot.com",
        messagingSenderId: "YOUR_SENDER_ID",
        appId: "YOUR_APP_ID",
        measurementId: "YOUR_MEASUREMENT_ID"
    };

    const vapidKey = 'YOUR_PUBLIC_VAPID_KEY';
    ```

### 5. Download YOLO Models
Ensure you have a YOLO model file (e.g., `yolov8n.pt`) in the `models/` directory.

### 6. Run the Application
```bash
# Development mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# OR using Python module
python -m app.main
```
Access the Web UI at `http://localhost:8000`.

## 📡 API & Socket Documentation

### WebSocket Events
The application maintains a persistent WebSocket connection at `/ws/data`.

*   **Server -> Client (Updates)**:
    Received periodically when counts change.
    ```json
    {
      "in_count": 12,
      "out_count": 8
    }
    ```

### REST API Endpoints

*   **`POST /offer`**:
    Initiates the WebRTC handshake.
    *   **Body**: `{"sdp": "...", "type": "offer", "model": "yolov8n.pt"}`
    *   **Response**: `{"sdp": "...", "type": "answer"}`

*   **`POST /reset_counter`**:
    Resets the in/out counters to 0.
    *   **Response**: `{"message": "Counters reset", "tracks_updated": 1}`

*   **`GET /models`**:
    Lists available YOLO models stored in the `models/` directory.
    *   **Response**: `{"models": ["yolov8n.pt", "yolov8m.pt"], "current": "..."}`

*   **`POST /subscribe`**:
    Subscribes an FCM token to push notifications.
    *   **Body**: `{"token": "fcm_token_string"}`

## 🖼 Demo

![Demo GIF Placeholder](docs/demo.gif)
*(Placeholder: Add a GIF demonstrating the real-time detection and counting process)*

## 🤝 Contributing
1.  Fork the repository.
2.  Create a feature branch (`git checkout -b feature/NewFeature`).
3.  Commit your changes (`git commit -m 'Add some NewFeature'`).
4.  Push to the branch (`git push origin feature/NewFeature`).
5.  Open a Pull Request.

## 📄 License
[MIT License](LICENSE)
