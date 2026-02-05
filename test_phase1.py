import cv2
import sys
from app.counter_logic import ObjectCounter

def main():
    print("Initializing ObjectCounter...")
    try:
        # Initialize counter
        # Using default 'yolov8n.pt' which will download if not found
        counter = ObjectCounter()
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    # Use webcam (0) or provide a video path
    source = 0
    if len(sys.argv) > 1:
        source = sys.argv[1]

    print(f"Opening source: {source}")
    cap = cv2.VideoCapture(source)
    
    if not cap.isOpened():
        print(f"Error: Could not open video source {source}")
        return

    print("Starting loop. Press 'q' to exit.")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("End of stream.")
                break

            # Process frame
            annotated_frame = counter.process_frame(frame)

            # Show results (will only work if a display is available, otherwise this might throw or do nothing)
            # In a headless environment this will fail. We'll wrap it.
            try:
                cv2.imshow("People Counter Phase 1", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except cv2.error:
                # Likely headless
                pass
                
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"Final Counts - In: {counter.in_count}, Out: {counter.out_count}")

if __name__ == "__main__":
    main()
