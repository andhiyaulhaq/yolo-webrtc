import av
from aiortc import MediaStreamTrack
import asyncio
from concurrent.futures import ThreadPoolExecutor
from .counter_logic import ObjectCounter

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an input track.
    It uses ObjectCounter to detect and count people.
    """
    kind = "video"

    def __init__(self, track, update_callback=None, model_path=None):
        super().__init__()
        self.track = track
        # Use provided model_path or let ObjectCounter decide (which defaults to env var)
        if model_path:
             self.counter = ObjectCounter(model_path=model_path)
        else:
             self.counter = ObjectCounter()
        self.update_callback = update_callback
        
        # Executor for running inference in a separate thread
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.inference_task = None

    async def recv(self):
        # Read the frame from the source track
        frame = await self.track.recv()

        # Convert to numpy array (OpenCV format)
        img = frame.to_ndarray(format="bgr24")

        # Check if inference is running
        loop = asyncio.get_event_loop()
        
        # If previous task is done, collect results and start new one
        if self.inference_task and self.inference_task.done():
            try:
                results = self.inference_task.result()
                self.counter.update_tracking(results)
                
                if self.update_callback:
                    self.update_callback(self.counter.in_count, self.counter.out_count)
            except Exception as e:
                print(f"Inference error: {e}")
            self.inference_task = None

        if self.inference_task is None:
            # Start new inference task
            # We pass a copy just to be absolutely safe against any modification,
            # though current code doesn't modify input.
            self.inference_task = loop.run_in_executor(self.executor, self.counter.predict, img.copy())

        # Annotate frame using current state (immediate return)
        annotated_img = self.counter.annotate_frame(img)

        # Convert back to av.VideoFrame
        new_frame = av.VideoFrame.from_ndarray(annotated_img, format="bgr24")
        
        # Preserve timing information
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base

        return new_frame
