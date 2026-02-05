import cv2
import numpy as np
from ultralytics import YOLO
from collections import deque

class ObjectCounter:
    def __init__(self, model_path='models/yolov8n.pt', region=None):
        """
        Initialize the ObjectCounter with a YOLO model and a counting region.
        
        Args:
            model_path (str): Path to the YOLO model file.
            region (list): List of points [(x1,y1), (x2,y2)] defining the counting line.
                           If None, defaults to a horizontal line in the middle of the frame.
        """
        # Load the YOLO model
        self.model = YOLO(model_path)
        
        # Region (Line) definition: [start_point, end_point]
        self.region = region 
        
        # Tracking data
        self.track_history = {} # id -> list of recent centroids
        self.counted_ids = set()
        
        # Counts
        self.in_count = 0
        self.out_count = 0
        
        
        # Frame Skipping (Removed in favor of async handling in Camera)
        self.last_boxes = []
        self.last_track_ids = []
        
        # Line Crossing Buffer (to avoid immediate re-triggering, though counted_ids handles one-time count)
        # We store history to determine direction

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
        A, B are points of the trajectory
        C, D are points of the counting line
        """
        def ccw(p1, p2, p3):
            return (p3[1] - p1[1]) * (p2[0] - p1[0]) > (p2[1] - p1[1]) * (p3[0] - p1[0])

        return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

    def _get_direction(self, p1, p2, line_start, line_end):
        """
        Determine direction of crossing using cross product approach.
        Returns 'in' or 'out'.
        """
        # We can define 'in' as moving from 'above' to 'below' the line or vice versa depending on needs.
        # Let's use the cross product of the line vector and the point vector to determine side.
        
        # Line vector
        line_vec = (line_end[0] - line_start[0], line_end[1] - line_start[1])
        
        # Check p1 position relative to line
        cross_p1 = line_vec[0] * (p1[1] - line_start[1]) - line_vec[1] * (p1[0] - line_start[0])
        
        # If cross_p1 is positive, it's on one side. 
        # We assume if it crossed, p2 is on the other side.
        # Let's say positive -> negative is 'in' (Entry)
        
        if cross_p1 < 0:
            return 'out'
        else:
            return 'in'

    def predict(self, frame):
        """
        Run inference on the frame.
        Returns:
            results: The YOLO results object (containing boxes, ids, etc.)
        """
        # Run tracking (detect + track)
        # persist=True is important for ID tracking
        results = self.model.track(frame, persist=True, verbose=False, classes=[0])
        return results

    def update_tracking(self, results):
        """
        Update tracking history and counts based on inference results.
        Should be called in the main thread to ensure state consistency.
        """
        if results and results[0].boxes.id is not None:
            self.last_boxes = results[0].boxes.xyxy.cpu().numpy()
            self.last_track_ids = results[0].boxes.id.cpu().numpy().astype(int)
        else:
            self.last_boxes = []
            self.last_track_ids = []

        # History / Track Logic
        if len(self.last_boxes) > 0:
            for box, track_id in zip(self.last_boxes, self.last_track_ids):
                x1, y1, x2, y2 = box
                cx, cy = self._calculate_centroid(x1, y1, x2, y2)
                
                if track_id not in self.track_history:
                    self.track_history[track_id] = []
                
                self.track_history[track_id].append((cx, cy))
                
                if len(self.track_history[track_id]) > 1:
                    prev_cx, prev_cy = self.track_history[track_id][-2]
                    curr_cx, curr_cy = (cx, cy)
                    
                    if track_id not in self.counted_ids:
                        line_start = self.region[0]
                        line_end = self.region[1]
                        if self._intersect((prev_cx, prev_cy), (curr_cx, curr_cy), line_start, line_end):
                            direction = self._get_direction((prev_cx, prev_cy), (curr_cx, curr_cy), line_start, line_end)
                            
                            if direction == 'in':
                                self.in_count += 1
                            else:
                                self.out_count += 1
                                
                            self.counted_ids.add(track_id)
                            
                            # Note: Visual feedback for counting is handled in annotate_frame 
                            # implicitly if we want to add a temporary marker, 
                            # but for now we trust the overlay text.

                if len(self.track_history[track_id]) > 30:
                    self.track_history[track_id].pop(0)

    def annotate_frame(self, frame):
        """
        Draw the virtual line, bounding boxes, and counts on the frame.
        Returns the annotated frame.
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
             # print(f"Resolution changed from {self.frame_width}x{self.frame_height} to {width}x{height}.")
             self.frame_width = width
             self.frame_height = height
             cx = int(width * 0.5)
             self.region = [(cx, 0), (cx, height)]

        if self.region is None:
             cx = int(width * 0.5)
             self.region = [(cx, 0), (cx, height)]

        line_start = self.region[0]
        line_end = self.region[1]

        # Draw Objects
        if len(self.last_boxes) > 0:
            for box, track_id in zip(self.last_boxes, self.last_track_ids):
                x1, y1, x2, y2 = box
                # Draw Box
                cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
                cv2.putText(annotated_frame, f"ID: {track_id}", (int(x1), int(y1)-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                # Draw centroid/trace if desired? (Optional)
                x1, y1, x2, y2 = box
                cx, cy = self._calculate_centroid(x1, y1, x2, y2)
                cv2.circle(annotated_frame, (cx, cy), 4, (0, 0, 255), -1)

        # Draw the virtual line
        cv2.line(annotated_frame, line_start, line_end, (255, 0, 0), 3)
        cv2.putText(annotated_frame, "Counting Line", (line_start[0], line_start[1] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)



        return annotated_frame

