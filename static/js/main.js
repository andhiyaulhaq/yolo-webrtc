// DOM Elements
const remoteVideo = document.getElementById('remoteVideo');
const startButton = document.getElementById('startButton');
const videoPlaceholder = document.getElementById('videoPlaceholder');
const connectionStatus = document.getElementById('connectionStatus');
const inCountDisplay = document.getElementById('inCount');
const outCountDisplay = document.getElementById('outCount');
const latencyVal = document.getElementById('latencyVal');
const fpsVal = document.getElementById('fpsVal');

// WebRTC Configuration
const config = {
    sdpSemantics: 'unified-plan',
    iceServers: [
        { urls: ['stun:stun.l.google.com:19302'] } // Public STUN server
    ]
};

let pc = null;
let ws = null;
let reconnectInterval = null;

// Helper function for status updates
function updateStatus(state) {
    const statusText = connectionStatus.querySelector('.status-text');
    connectionStatus.className = 'connection-status ' + state;

    if (state === 'connected') {
        statusText.textContent = 'Live';
    } else if (state === 'connecting') {
        statusText.textContent = 'Connecting...';
        connectionStatus.classList.add('connecting'); // You might want to add animation
    } else {
        statusText.textContent = 'Disconnected';
    }
}

// WebSocket Connection
function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/data`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.in_count !== undefined) {
                // Animate numbers? Simple text update for now
                inCountDisplay.textContent = data.in_count;
                outCountDisplay.textContent = data.out_count;
            }
        } catch (e) {
            console.error('Error parsing WS message:', e);
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected. Reconnecting in 3s...');
        setTimeout(connectWebSocket, 3000);
    };
}

let lastValidResolution = 'vga';

// WebRTC Negotiation
async function startStream() {
    updateStatus('connecting');
    startButton.disabled = true;

    // valid states: closed, failed, disconnected, new
    if (pc) {
        pc.close();
    }

    // ... (rest of function setup)
    pc = new RTCPeerConnection(config);

    // Handle incoming track (Annotated Video from Server)
    pc.ontrack = (evt) => {
        // ... (same as before)
        console.log('Track received:', evt.track.kind);
        if (evt.track.kind === 'video') {
            remoteVideo.srcObject = evt.streams[0];
            videoPlaceholder.classList.add('hidden');
            updateStatus('connected');
        }
    };

    pc.oniceconnectionstatechange = () => {
        console.log('ICE State:', pc.iceConnectionState);
        if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'disconnected') {
            updateStatus('disconnected');
            videoPlaceholder.classList.remove('hidden');
            startButton.disabled = false;
        }
    };

    const resSelect = document.getElementById('resSelect');
    const resValue = resSelect ? resSelect.value : 'vga';

    try {
        // Create specific constraints based on resolution choice
        let constraints = {
            video: {
                facingMode: 'environment'
            },
            audio: false
        };

        if (resValue === 'qvga') {
            constraints.video.width = { ideal: 320, max: 320 };
            constraints.video.height = { ideal: 240, max: 240 };
        } else if (resValue === 'vga') {
            constraints.video.width = { ideal: 640, min: 640 };
            constraints.video.height = { ideal: 480, min: 480 };
        } else if (resValue === 'hd') {
            constraints.video.width = { ideal: 1280, min: 1280 };
            constraints.video.height = { ideal: 720, min: 720 };
        } else if (resValue === 'fhd') {
            constraints.video.width = { ideal: 1920, min: 1920 };
            constraints.video.height = { ideal: 1080, min: 1080 };
        }

        // Get Local Stream (Camera)
        let localStream;
        try {
            localStream = await navigator.mediaDevices.getUserMedia(constraints);
            // If successful, update our last known good resolution
            lastValidResolution = resValue;
        } catch (err) {
            console.warn("Resolution not supported:", resValue, err);

            // Revert UI
            if (resSelect) resSelect.value = lastValidResolution;

            showToast('Resolution Unsupported', `Your camera does not support ${resValue.toUpperCase()}. Reverting to ${lastValidResolution.toUpperCase()}.`, 5000);

            // Fallback attempt (recursive? or just retry with old constraints logic here)
            // Simpler: Just recursively call startStream() effectively retrying with the reverted value
            // But verify we don't loop infinitely. Check if we already reverted.
            if (resValue !== lastValidResolution) {
                console.log("Retrying with fallback resolution...");
                startButton.disabled = false; // reset state for next attempt
                return startStream();
            } else {
                throw err; // If even the fallback fails, escalate
            }
        }

        const track = localStream.getVideoTracks()[0];
        const settings = track.getSettings();
        console.log(`Requested constraints:`, JSON.stringify(constraints));
        console.log(`Actual resolution: ${settings.width}x${settings.height}`);
        updateStatus(`Camera: ${settings.width}x${settings.height}`);

        // Add local track to PC
        // This triggers 'on_track' on the server side
        localStream.getTracks().forEach(track => {
            pc.addTrack(track, localStream);
        });

        // Create Offer
        const offer = await pc.createOffer();

        // Force VP8 Codec
        let sdp = offer.sdp;
        // Simple SDP munging to prioritize VP8
        // This regex finds the payload type for VP8 and moves it to the front of the m=video line
        const lines = sdp.split('\n');
        let vp8Payload = null;

        // Find VP8 payload type
        /* 
           Looking for: a=rtpmap:<payload> VP8/90000 
        */
        for (let line of lines) {
            if (line.includes('VP8/90000')) {
                const match = line.match(/a=rtpmap:(\d+) VP8\/90000/);
                if (match && match[1]) {
                    vp8Payload = match[1];
                    break;
                }
            }
        }

        if (vp8Payload) {
            console.log("Forcing VP8 Payload:", vp8Payload);
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].startsWith('m=video')) {
                    // m=video <port> <proto> <payloads>...
                    // Remove VP8 from list and add to front
                    let parts = lines[i].split(' ');
                    // keep first 3 parts (m=video, port, proto)
                    const header = parts.slice(0, 3);
                    const payloads = parts.slice(3);

                    const newPayloads = payloads.filter(p => p !== vp8Payload);
                    newPayloads.unshift(vp8Payload);

                    lines[i] = header.concat(newPayloads).join(' ');
                    break;
                }
            }
            sdp = lines.join('\n');
        }

        const offerWithVP8 = {
            type: offer.type,
            sdp: sdp
        };

        await pc.setLocalDescription(offerWithVP8);

        // Wait for ICE gathering to complete (simple approach) or rely on server handling
        await new Promise((resolve) => {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                const checkState = () => {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                };
                pc.addEventListener('icegatheringstatechange', checkState);
                // Fallback timeout in case 'complete' never fires (some browsers)
                setTimeout(resolve, 2000);
            }
        });

        const localDesc = pc.localDescription;

        // Send to server
        const response = await fetch('/offer', {
            method: 'POST',
            body: JSON.stringify({
                sdp: localDesc.sdp,
                type: localDesc.type,
                model: document.getElementById('modelSelect').value
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const answer = await response.json();
        await pc.setRemoteDescription(answer);

    } catch (e) {
        console.error('Failed to start stream:', e);
        updateStatus('disconnected');
        startButton.disabled = false;
        startButton.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                stroke-linejoin="round">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            Start Analysis
        `;
        alert('Could not start stream. ' + e.message);
    }
}

// Start Stats Interval
setInterval(() => {
    if (pc && pc.connectionState === 'connected') {
        pc.getStats().then(stats => {
            stats.forEach(report => {
                if (report.type === 'inbound-rtp' && report.kind === 'video') {
                    // Update FPS if available
                    if (report.framesPerSecond) {
                        fpsVal.textContent = Math.round(report.framesPerSecond);
                    }
                }
                if (report.type === 'candidate-pair' && report.state === 'succeeded') {
                    // Update Latency (Round Trip Time)
                    if (report.currentRoundTripTime) {
                        latencyVal.textContent = Math.round(report.currentRoundTripTime * 1000) + ' ms';
                    }
                }
            });
        });
    }
}, 1000);


// Initialize
startButton.addEventListener('click', () => {
    // Show loading state
    startButton.innerHTML = `<span class="spinner"></span> Connecting...`;
    startButton.disabled = true;
    startStream();
});

// Auto-restart stream on settings change
const settingsElements = [document.getElementById('modelSelect'), document.getElementById('resSelect')];
settingsElements.forEach(el => {
    if (el) {
        el.addEventListener('change', () => {
            // Only restart if the stream is already running (connected or checking)
            if (pc && (pc.connectionState === 'connected' || pc.connectionState === 'checking')) {
                console.log('Settings changed, restarting stream...');
                showToast('Updating Stream', 'Applying new settings...', 3000);
                startStream();
            }
        });
    }
});
connectWebSocket();

// --- Firebase Cloud Messaging (Web Push) ---
const enableNotificationsBtn = document.getElementById('enableNotifications');

// TODO: Paste your Firebase config object here EXACTLY as in firebase-messaging-sw.js
// Config is now loaded from js/config.js

try {
    console.log("Initializing Firebase...");
    firebase.initializeApp(firebaseConfig);
    const messaging = firebase.messaging();
    console.log("Firebase initialized.");

    // Handle foreground messages
    messaging.onMessage((payload) => {
        console.log('[main.js] Foreground message received ', payload);
        const { title, body } = payload.notification;
        showToast(title, body);
    });

    enableNotificationsBtn.addEventListener('click', () => {
        console.log("Button clicked. Requesting permission...");
        Notification.requestPermission().then((permission) => {
            if (permission === 'granted') {
                console.log('Notification permission granted.');

                // Register Service Worker explicitly
                navigator.serviceWorker.register('./firebase-messaging-sw.js')
                    .then((registration) => {
                        console.log('Service Worker registered with scope:', registration.scope);

                        // Get Token with registration
                        return messaging.getToken({
                            vapidKey: vapidKey,
                            serviceWorkerRegistration: registration
                        });
                    })
                    .then((currentToken) => {
                        if (currentToken) {
                            console.log('FCM Token:', currentToken);
                            sendTokenToServer(currentToken);
                            enableNotificationsBtn.textContent = "Notifications Enabled";
                            enableNotificationsBtn.disabled = true;
                        } else {
                            console.log('No registration token available. Request permission to generate one.');
                        }
                    }).catch((err) => {
                        console.log('An error occurred while retrieving token. ', err);
                    });

            } else {
                console.log('Unable to get permission to notify.');
                alert("Permission denied. We cannot send you alerts.");
            }
        });
    });

} catch (e) {
    console.warn("Firebase not initialized in main.js (Missing config?)", e);
    // Hide button if config missing
    // enableNotificationsBtn.style.display = 'none'; 
}

function sendTokenToServer(token) {
    fetch('/subscribe', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ token: token })
    })
        .then(response => response.json())
        .then(data => console.log('Server subscription response:', data))
        .catch((error) => console.error('Error subscribing to topic:', error));
}

function showToast(title, body) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-header">
            <span class="toast-title">
                ⚠️ ${title}
            </span>
            <span style="font-size: 0.8rem; opacity: 0.7;">Now</span>
        </div>
        <div class="toast-body">${body}</div>
    `;

    // Click to dismiss
    toast.addEventListener('click', () => {
        toast.classList.add('hiding');
        toast.addEventListener('animationend', () => toast.remove());
    });

    // Auto dismiss after 5 seconds
    setTimeout(() => {
        if (toast.isConnected) {
            toast.classList.add('hiding');
            toast.addEventListener('animationend', () => toast.remove());
        }
    }, 5000);

    container.appendChild(toast);
}

// Fetch available models

