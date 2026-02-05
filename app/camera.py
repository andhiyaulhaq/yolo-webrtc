import av
from aiortc import MediaStreamTrack
from .counter_logic import ObjectCounter

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an input track.
    It uses ObjectCounter to detect and count people.
    """
    kind = "video"

    def __init__(self, track, update_callback=None):
        super().__init__()
        self.track = track
        self.counter = ObjectCounter()
        self.update_callback = update_callback

    async def recv(self):
        # Read the frame from the source track
        frame = await self.track.recv()

        # Convert to numpy array (OpenCV format)
        img = frame.to_ndarray(format="bgr24")

        # Process the frame using ObjectCounter
        # This will update counts and return an annotated image
        annotated_img = self.counter.process_frame(img)

        # Trigger callback with current counts
        if self.update_callback:
             # We can check if counts changed to minimize traffic, 
             # but strictly speaking broadcasting current state is fine.
             # Ideally we check change in process_frame but accessing properties is cheap.
             self.update_callback(self.counter.in_count, self.counter.out_count)

        # Convert back to av.VideoFrame
        new_frame = av.VideoFrame.from_ndarray(annotated_img, format="bgr24")
        
        # Preserve timing information
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base

        return new_frame
