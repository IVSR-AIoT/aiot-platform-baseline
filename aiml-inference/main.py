import os
import sys
import shutil
import time
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
import torch
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from queue import Queue
from threading import Thread

import torch_tensorrt
from message_broker.rabbitmq import publishMessage
from yolo_engine.yolo import load_engine

import redis
import json


def create_model():
    """
    Load and prepare the AI model using a custom engine loader.

    Returns:
        torch.nn.Module: Loaded and configured AI model.
    """
    model = load_engine()
    # model.to(DEVICE).half().eval()
    return model


# Load environment variables from .env file
load_dotenv()

# Configuration Parameters
MODEL_PATH = os.getenv(
    'MODEL_PATH', 'last_model.pth')
MODEL_SAVE_PATH = os.getenv('MODEL_SAVE_PATH', 'ssd300_traced.pt')

VIDEO_SOURCE = os.getenv('VIDEO_SOURCE', 'rtsp://admin:ivsr2019@192.168.1.100')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 8))
FRAME_WIDTH = int(os.getenv('FRAME_WIDTH', 640))
FRAME_HEIGHT = int(os.getenv('FRAME_HEIGHT', 640))
QUEUE_SIZE = int(os.getenv('QUEUE_SIZE', 100))
NUM_WORKERS = int(os.getenv('NUM_WORKERS', 2))
DEVICE = os.getenv('DEVICE', 'cuda' if torch.cuda.is_available() else 'cpu')
PRECISION = os.getenv('PRECISION', 'fp16')
SAVE_IMAGE_PATH = os.getenv('SAVE_IMAGE_PATH', './saved_images')

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT'))
REDIS_DB = os.getenv('REDIS_DB')

detection_polygon = []  # List of tuples
use_detection_polygon = True


def getDetectionPolygon():

    global detection_polygon, use_detection_polygon
    detection_polygon_str = None

    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

    try:
        detection_polygon_str = str(redis_client.get(
            'detection_range').decode('utf-8'))

        points_list = json.loads(detection_polygon_str)

        detection_polygon = [(p["x"], p["y"]) for p in points_list]
        print(f"Detection polygon: {detection_polygon}")

    except Exception as e:
        print(f"[EX]: When read data from redis db: {e}")
        print(f"[ERR]: Will not use detection polygon")
        use_detection_polygon = False


getDetectionPolygon()

# Initialize the AI model
model = create_model()

# Uncomment and modify the following if you plan to use Torch-TensorRT
# traced_model = torch.jit.trace(model, [torch.randn((1, 3, FRAME_HEIGHT, FRAME_WIDTH)).to(DEVICE).half()])
# traced_model.save(MODEL_SAVE_PATH)
# trt_model = torch_tensorrt.compile(
#     traced_model,
#     inputs=[torch_tensorrt.Input((1, 3, FRAME_HEIGHT, FRAME_WIDTH), dtype=torch.half)],
#     enabled_precisions={torch.half},  # Run with FP16
#     workspace_size=1 << 20
# )


class FastVideoProcessor:
    """
    High-performance video capture and processing for AI inference.

    Features:
        - Multi-threaded capture and preprocessing
        - Efficient GPU memory management
        - Batch processing
        - Automatic frame dropping if AI can't keep up
    """

    def __init__(
        self,
        source: str = VIDEO_SOURCE,
        batch_size: int = BATCH_SIZE,
        width: int = FRAME_WIDTH,
        height: int = FRAME_HEIGHT,
        num_workers: int = NUM_WORKERS,
        queue_size: int = QUEUE_SIZE,
        device: str = DEVICE
    ):
        """
        Initialize the FastVideoProcessor.

        Args:
            source (str): Video source identifier or RTSP URL.
            batch_size (int): Number of frames per batch.
            width (int): Frame width.
            height (int): Frame height.
            num_workers (int): Number of worker threads.
            queue_size (int): Maximum size of the frame queue.
            device (str): Device to use for processing.
        """
        self.device = device
        self.batch_size = batch_size
        self.stopped = False

        # Initialize video capture
        self.cap = cv2.VideoCapture(source)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)

        # Check if camera opened successfully
        if not self.cap.isOpened():
            raise IOError("Failed to open video source")

        self.width = width
        self.height = height

        # Initialize queues
        self.frame_queue = Queue(maxsize=queue_size)
        self.batch_queue = Queue(maxsize=2)

        # Pre-allocate tensors on GPU
        self.gpu_batch = torch.zeros(
            (batch_size, 3, self.height, self.width),
            dtype=torch.float16,
            device=device
        )

        # Pre-allocate pinned memory on CPU for faster transfer
        self.pinned_batch = torch.zeros(
            (batch_size, 3, self.height, self.width),
            dtype=torch.float16
        ).pin_memory()

        # Start worker threads
        self.capture_thread = Thread(target=self._capture_frames, daemon=True)
        self.batch_thread = Thread(target=self._prepare_batches, daemon=True)
        self.executor = ThreadPoolExecutor(max_workers=num_workers)

        self.start()

    def start(self):
        """
        Start all worker threads for capturing and preparing batches.
        """
        self.capture_thread.start()
        self.batch_thread.start()

    def _capture_frames(self):
        """
        Continuously capture frames from the video source in a separate thread.
        """
        while not self.stopped:
            if not self.frame_queue.full():
                ret, frame = self.cap.read()
                if ret:
                    frame = cv2.resize(frame, (self.width, self.height))
                    self.frame_queue.put(frame)
                else:
                    self.stopped = True
                    break
            else:
                time.sleep(0.001)  # Prevent CPU spin when queue is full

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Preprocess a single frame efficiently.

        Args:
            frame (np.ndarray): Input frame.

        Returns:
            np.ndarray: Preprocessed frame.
        """
        # If color conversion is not needed, skip it
        # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = np.ascontiguousarray(frame)
        frame = frame.transpose(2, 0, 1)  # HWC to CHW
        frame = frame.astype(np.float16) / 255.0
        return frame

    def _prepare_batches(self):
        """
        Prepare batches of frames for AI processing.
        """
        batch_frames = []

        while not self.stopped:
            # Collect frames for the batch
            while len(batch_frames) < self.batch_size and not self.stopped:
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get()
                    batch_frames.append(frame)
                else:
                    time.sleep(0.001)

            if batch_frames:
                # Process frames
                processed_frames = [self._preprocess_frame(
                    frame) for frame in batch_frames]

                # Convert to tensor using pinned memory
                for i, processed in enumerate(processed_frames):
                    self.pinned_batch[i].copy_(torch.from_numpy(processed))

                # Transfer to GPU
                if self.device == 'cuda':
                    with torch.cuda.stream(torch.cuda.Stream()):
                        self.gpu_batch.copy_(
                            self.pinned_batch, non_blocking=True)
                        if not self.batch_queue.full():
                            self.batch_queue.put(self.gpu_batch.clone())
                else:
                    if not self.batch_queue.full():
                        self.batch_queue.put(self.pinned_batch.clone())

                batch_frames = []

    def get_batch(self, timeout: float = 1.0) -> Optional[torch.Tensor]:
        """
        Retrieve the next batch of frames as a tensor on the specified device.

        Args:
            timeout (float): Timeout in seconds.

        Returns:
            Optional[torch.Tensor]: Tensor of shape (batch_size, 3, height, width) or None if timeout occurs.
        """
        try:
            return self.batch_queue.get(timeout=timeout)
        except:
            return None

    def release(self):
        """
        Release all resources, including threads and video capture.
        """
        self.stopped = True
        self.capture_thread.join()
        self.batch_thread.join()
        self.executor.shutdown()
        self.cap.release()


def demo():
    """
    Example usage of FastVideoProcessor with FPS monitoring and AI inference.
    """
    global use_detection_polygon, detection_polygon

    processor = FastVideoProcessor()
    try:
        frames_processed = 0
        fps_update_interval = 1.0  # Update FPS every second
        count_frame = 0
        start_time_fps = time.time()
        start_time = time.time()
        count = 0

        while True:
            getDetectionPolygon()
            batch = processor.get_batch(timeout=1.0)

            if batch is None:
                continue

            # AI model inference
            output = model(batch)

            # Post-processing
            for i in range(batch.size(0)):
                bboxes = output[i].boxes.xyxy.cpu().numpy()

                if bboxes.shape[0] == 0:
                    continue
                else:
                    save_time = time.time() - start_time
                    print(
                        f'count: {count}, save_time: {save_time:.2f} seconds')

                    if save_time > 10:
                        start_time = time.time()
                        count = 0

                    if count < 5 and save_time < 1:
                        count += 1
                        timestamp = datetime.now().isoformat()

                        for index, bbox in enumerate(bboxes):
                            x1, y1, x2, y2 = bbox
                            # Draw rectangle on the original image
                            cv2.rectangle(output[i].orig_img, (int(x1), int(y1)),
                                          (int(x2), int(y2)), (0, 255, 0), 2)

                            # Prepare message payload
                            message = {
                                "id": index,
                                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                                "type": "Human",
                                "timestamp": timestamp
                            }
                            publishMessage(message)

                        # If detection polygon is enabled, draw it
                        if use_detection_polygon and detection_polygon:
                            polygon_points = np.array(
                                detection_polygon, np.int32)
                            polygon_points = polygon_points.reshape((-1, 1, 2))

                            # Draw the polygon with dotted lines (red color)
                            cv2.polylines(output[i].orig_img, [polygon_points],
                                          isClosed=True, color=(0, 0, 255), thickness=2, lineType=cv2.LINE_AA)

                        # Construct the filename with timestamp
                        filename = os.path.join(
                            SAVE_IMAGE_PATH,
                            f"{timestamp}.jpg"
                        )

                        # Save the image with bounding boxes and detection polygon
                        cv2.imwrite(filename, output[i].orig_img)
                        print("Image saved successfully.")
                    elif count >= 5 and save_time >= 1:
                        count = 0
                        start_time = time.time()

            frames_processed += batch.size(0)

            # Calculate and print FPS
            elapsed = time.time() - start_time_fps
            if elapsed >= fps_update_interval:
                fps = frames_processed / elapsed
                print(f"Processing FPS: {fps:.2f}")
                frames_processed = 0
                start_time_fps = time.time()

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        processor.release()


if __name__ == "__main__":
    # Check if the folder exists; if so, remove it's contents
    for entry in os.listdir(SAVE_IMAGE_PATH):
        entry_path = os.path.join(SAVE_IMAGE_PATH, entry)
        try:
            if os.path.isfile(entry_path) or os.path.islink(entry_path):
                os.unlink(entry_path)  # Remove file or symlink
            elif os.path.isdir(entry_path):
                shutil.rmtree(entry_path)  # Remove directory and its contents
        except Exception as e:
            print(f"Failed to delete {entry_path}. Reason: {e}")

    demo()
