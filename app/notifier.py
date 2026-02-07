import firebase_admin
from firebase_admin import credentials, messaging
import logging
import os
import time
import threading

logger = logging.getLogger(__name__)

class Notifier:
    def __init__(self, cred_path="firebase_creds.json"):
        self.mock_mode = False
        self.last_alert_time = 0
        self.cooldown = int(os.getenv("ALERT_COOLDOWN_SECONDS", 300))
        self._lock = threading.Lock()  # Lock for thread safety

        if not os.path.exists(cred_path):
            logger.warning(f"'{cred_path}' not found. Notifier running in MOCK MODE (logging only).")
            self.mock_mode = True
            return

        try:
            cred = credentials.Certificate(cred_path)
            # Check if app is already initialized to avoid "app already exists" error on reload
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin: {e}")
            self.mock_mode = True

    def send_alert(self, current_count, threshold):
        """
        Sends an alert if the cooldown period has passed.
        Thread-safe to prevent race conditions.
        """
        with self._lock:  # Ensure only one thread checks/updates at a time
            now = time.time()
            if now - self.last_alert_time < self.cooldown:
                return

            message_body = f"Alert! Count exceeded limit. Current: {current_count} (Limit: {threshold})"
            
            if self.mock_mode:
                logger.info(f"[MOCK ALERT] {message_body}")
                self.last_alert_time = now
                return

            # Real FCM logic
            try:
                # Topic 'alerts' is generic; client apps would subscribe to this topic
                message = messaging.Message(
                    notification=messaging.Notification(
                        title="Crowd Limit Exceeded",
                        body=message_body,
                    ),
                    topic="alerts",
                )
                response = messaging.send(message)
                logger.info(f"Successfully sent FCM message: {response}")
                self.last_alert_time = now # Update time only after success (or before if you want strict rate limiting)
            except Exception as e:
                logger.error(f"Error sending FCM message: {e}")
