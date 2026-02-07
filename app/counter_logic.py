import cv2
import numpy as np
import torch
from ultralytics import YOLO

# Limit CPU usage to prevent video lag
torch.set_num_threads(2)
from collections import deque
import time
from app.database import log_crossing, log_alert

class KalmanBoxTracker:
    """
    A simple Kalman Filter for tracking bounding boxes in image space.
    State: [x, y, w, h, dx, dy, dw, dh]
    Measurement: [x, y, w, h]
    """
    def __init__(self, bbox):
        # Initialize Kalman Filter
        # Dynamo = 8 (x, y, w, h, vx, vy, vw, vh)
        # Measure = 4 (x, y, w, h)
        self.kf = cv2.KalmanFilter(8, 4)
        
        # Transition Matrix (F)
        # x = x + vx, etc.
        self.kf.transitionMatrix = np.array([
            [1, 0, 0, 0, 1, 0, 0, 0],
            [0, 1, 0, 0, 0, 1, 0, 0],
            [0, 0, 1, 0, 0, 0, 1, 0],
            [0, 0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0, 1]
        ], np.float32)

        # Measurement Matrix (H)
        # We measure x, y, w, h directly
        self.kf.measurementMatrix = np.array(np.eye(4, 8), np.float32)

        # Process Noise Covariance (Q)
        # Controls how much we trust the model evolution
        self.kf.processNoiseCov = np.array(np.eye(8, 8), np.float32) * 1e-2
        # Velocity terms might change faster
        self.kf.processNoiseCov[4:, 4:] *= 5.0

        # Measurement Noise Covariance (R)
        # Controls how much we trust the measurement
        self.kf.measurementNoiseCov = np.array(np.eye(4, 4), np.float32) * 1e-1

        # Error Covariance (P)
        self.kf.errorCovPost = np.eye(8, dtype=np.float32)

        # Initial State
        x, y, x2, y2 = bbox
        w = x2 - x
        h = y2 - y
        self.kf.statePost = np.array([[x], [y], [w], [h], [0], [0], [0], [0]], np.float32)
        
        self.time_since_update = 0
        self.history = []
        self.hits = 0
        self.hit_streak = 0
        self.age = 0
        
        # Keep track of last predicted box for smooth rendering
        self.pred_box = bbox
        
        # Cooldown for counting
        self.last_counted_time = 0

    def update(self, bbox):
        """
        Updates the state vector with observed bbox.
        """
        self.time_since_update = 0
        self.history = []
        self.hits += 1
        self.hit_streak += 1
        x, y, x2, y2 = bbox
        w = x2 - x
        h = y2 - y
        measurement = np.array([[x], [y], [w], [h]], np.float32)
        self.kf.correct(measurement)

    def predict(self):
        """
        Advances the state vector and returns the predicted bounding box.
        """
        if((self.kf.statePost[6]+self.kf.statePost[2])<=0):
            self.kf.statePost[6] *= 0.0
        
        self.kf.predict()
        self.age += 1
        if(self.time_since_update>0):
            self.hit_streak = 0
        self.time_since_update += 1
        
        # Return predicted box
        s = self.kf.statePost
        x, y, w, h = s[0][0], s[1][0], s[2][0], s[3][0]
        
        self.pred_box = [x, y, x + w, y + h]
        self.history.append(self.pred_box)
        return self.pred_box

    def get_state(self):
        """
        Returns the current bounding box estimate.
        """
        s = self.kf.statePost
        x, y, w, h = s[0][0], s[1][0], s[2][0], s[3][0]
        return [x, y, x + w, y + h]

class ObjectCounter:
    def __init__(self, model_path=None, region=None):
        """
        Initialize the ObjectCounter with a YOLO model and a counting region.
        
        Args:
            model_path (str): Path to the YOLO model file.
            region (list): List of points [(x1,y1), (x2,y2)] defining the counting line.
                           If None, defaults to a horizontal line in the middle of the frame.
        """
        # Load the YOLO model
        import os
        if model_path is None:
            model_path = os.getenv('YOLO_MODEL', 'models/yolov8n.pt')
        
        self.model = YOLO(model_path)
        
        # Region (Line) definition: [start_point, end_point]
        self.region = region 
        
        # Tracking data
        # self.track_history = {} # OLD: id -> list of recent centroids
        self.tracks = {} # id -> KalmanBoxTracker
        # self.counted_ids = set() # Removed in favor of timed cooldown logic
        
        # Counts
        self.in_count = 0
        self.out_count = 0
        
        # Temporary storage for latest detection results to sync with main thread
        self.latest_results = None
        
        # History for drawing trails (optional)
        self.trail_history = {} 

    def set_region(self, region):
        """
        Update the counting line coordinates.
        region: [(x1, y1), (x2, y2)]
        """
        self.region = region

    def _calculate_centroid(self, x1, y1, x2, y2):
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    def _intersect(self, A, B, C, D):
        """
        Return true if line segments AB and CD intersect
        """
        def ccw(p1, p2, p3):
            # Check for collinear points to avoid division by zero or errors
            # BUT for this simple case, standard CCW is fine.
            return (p3[1] - p1[1]) * (p2[0] - p1[0]) > (p2[1] - p1[1]) * (p3[0] - p1[0])

        return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

    def _get_direction(self, p1, p2, line_start, line_end):
        """
        Determine direction of crossing using cross product approach.
        Returns 'in' or 'out'.
        """
        line_vec = (line_end[0] - line_start[0], line_end[1] - line_start[1])
        cross_p1 = line_vec[0] * (p1[1] - line_start[1]) - line_vec[1] * (p1[0] - line_start[0])
        
        if cross_p1 < 0:
            return 'in'
        else:
            return 'out'

    def predict(self, frame):
        """
        Run inference on the frame.
        Returns:
            results: The YOLO results object
        """
        # Run tracking (detect + track)
        results = self.model.track(frame, persist=True, verbose=False, classes=[0])
        return results

    def update_tracking(self, results):
        """
        Update tracking history and counts based on inference results.
        Should be called in the main thread or a thread-safe manner.
        """
        self.latest_results = results # Store for debug if needed

        detected_ids = []
        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)
            
            for box, track_id in zip(boxes, track_ids):
                detected_ids.append(track_id)
                
                # Create or Update Tracker
                if track_id not in self.tracks:
                    self.tracks[track_id] = KalmanBoxTracker(box)
                else:
                    self.tracks[track_id].update(box)
        
        # Remove tracks that are lost (optional: separate cleanup logic)
        # For now, we rely on the age/time_since_update in annotate_frame to decide what to draw
        
        # We can proactively remove very old tracks here to save memory
        track_ids_to_remove = []
        for tid, trk in self.tracks.items():
            if trk.time_since_update > 60: # Missing for ~2 seconds at 30fps
                 track_ids_to_remove.append(tid)
        
        for tid in track_ids_to_remove:
            del self.tracks[tid]


    def annotate_frame(self, frame):
        """
        Draw the virtual line, bounding boxes, and counts on the frame.
        Uses Kalman Filter prediction for smooth updates.
        """
        annotated_frame = frame.copy()
        height, width = annotated_frame.shape[:2]

        # Initialize/Adjust region logic
        if not hasattr(self, 'frame_width') or not hasattr(self, 'frame_height'):
            self.frame_width = width
            self.frame_height = height
            if self.region is None:
                cx = int(width * 0.5)
                self.region = [(cx, 0), (cx, height)]

        # Dynamic Line Adjustment
        if width != self.frame_width or height != self.frame_height:
             self.frame_width = width
             self.frame_height = height
             cx = int(width * 0.5)
             self.region = [(cx, 0), (cx, height)]

        if self.region is None:
             cx = int(width * 0.5)
             self.region = [(cx, 0), (cx, height)]

        line_start = self.region[0]
        line_end = self.region[1]

        # --- PREDICT & DRAW TRACKS ---
        # Draw Objects based on Kalman Prediction
        # This function is called every video frame.
        
        # We iterate over all active trackers
        
        for track_id, tracker in self.tracks.items():
            # Hide tracks that haven't been seen in a while to avoid ghosting
            if tracker.time_since_update > 15: # Hide if missing for >0.5s (approx)
                continue
                
            # PREDICT NEXT POSITION
            # This advances the KF state. 
            # Note: If inference is slow, we might predict multiple times 
            # effectively extrapolating strictly based on velocity.
            # When inference returns, 'update()' will correct the state.
            pred_box = tracker.predict()
            
            # Extract coordinates from prediction (can be float)
            # pred_box returns [x1, y1, x2, y2]
            # It might return arrays, so ensure scalars
            x1 = float(pred_box[0])
            y1 = float(pred_box[1])
            x2 = float(pred_box[2])
            y2 = float(pred_box[3])
            
            # --- COUNTING LOGIC (Using Predicted Centroids) ---
            cx, cy = self._calculate_centroid(x1, y1, x2, y2)
            
            # Hide if centroid is out of frame to prevent ghosting
            if cx < 0 or cx >= width or cy < 0 or cy >= height:
                continue
            
            # Track Trail
            if track_id not in self.trail_history:
                self.trail_history[track_id] = []
            self.trail_history[track_id].append((cx, cy))
            if len(self.trail_history[track_id]) > 30:
                self.trail_history[track_id].pop(0)

            # Check Crossing
            if len(self.trail_history[track_id]) > 1:
                prev_cx, prev_cy = self.trail_history[track_id][-2]
                curr_cx, curr_cy = (cx, cy)
                
                if track_id not in self.tracks:
                     continue
                tracker = self.tracks[track_id]
                
                # Cooldown check (prevent jitter double counting)
                current_time = time.time()
                if (current_time - tracker.last_counted_time) > 1.0:
                    if self._intersect((prev_cx, prev_cy), (curr_cx, curr_cy), line_start, line_end):
                        direction = self._get_direction((prev_cx, prev_cy), (curr_cx, curr_cy), line_start, line_end)
                        if direction == 'in':
                            self.in_count += 1
                            log_crossing('in', track_id) # Log to DB
                        else:
                            self.out_count += 1
                            log_crossing('out', track_id) # Log to DB
                        # Update cooldown timer
                        tracker.last_counted_time = current_time

            # --- DRAWING ---
            cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
            # Show ID and maybe "Pred" to indicate it's predictive
            cv2.putText(annotated_frame, f"ID: {track_id}", (int(x1), int(y1)-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # Draw centroid
            cv2.circle(annotated_frame, (cx, cy), 4, (0, 0, 255), -1)


        # Draw the virtual line
        cv2.line(annotated_frame, line_start, line_end, (255, 0, 0), 3)
        cv2.putText(annotated_frame, "Counting Line", (line_start[0], line_start[1] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        return annotated_frame
