from ultralytics import YOLO
import torch
import torch_tensorrt
import time
import os

import redis
from . import config

r = redis.Redis(host=config.REDIS_HOST,
                port=config.REDIS_PORT, db=config.REDIS_DB)

r.set('MODEL_DESCRIPTION', config.MODEL_DESCRIPTION)
r.set('CAMERA_ID', config.CAMERA_ID)
r.set('CAMERA_TYPE', config.CAMERA_TYPE)


def export_engine():
    # Load a YOLO11n PyTorch model
    model = YOLO("yolo_person.pt")
    # Export the model to TensorRT
    model.export(format="engine", dynamic=True,  batch=8,
                 workspace=4,  half=True,)  # creates 'yolo11n.engine'


def load_engine():
    # Load the exported TensorRT model
    path = os.getcwd() + "/yolo_engine/yolo_person.engine"
    trt_model = YOLO(path)

    return trt_model


def run_engine():
    input_ = torch.rand(8, 3, 640, 640)
    # Load the exported TensorRT model
    trt_model = YOLO("yolo_person.engine")

    # Run inference
    results = trt_model(input_)


def load_torchscript():
    # Load a YOLO11n PyTorch model
    model = YOLO("yolo11n.pt")
    # Export the model to TensorRT
    model.export(format="torchscript")


def run_torchscript():
    input_ = torch.rand(8, 3, 640, 640)
    # Load the exported TensorRT model
    trt_model = YOLO("yolo11n.torchscript")

    # Run inference
    results = trt_model(input_)


def convert_ts_torchTRT():  # error function
    script_model = YOLO("yolo11n.torchscript")
    spec = {
        "forward": torch_tensorrt.ts.TensorRTCompileSpec(
            **{
                "inputs": [torch_tensorrt.Input([8, 3, 640, 640])],
                "enabled_precisions": {torch.float, torch.half},
                "refit": False,
                "debug": False,
                "device": {
                    "device_type": torch_tensorrt.DeviceType.GPU,
                    "gpu_id": 0,
                    "dla_core": 0,
                    "allow_gpu_fallback": True,
                },
                "capability": torch_tensorrt.EngineCapability.default,
                "num_avg_timing_iters": 1,
            }
        )
    }
    trt_model = torch_tensorrt.compile(
        script_model,
        inputs=[torch_tensorrt.Input((8, 3, 640, 640))],  # Example input shape
        # Change precision as needed (e.g., torch.half for FP16)
        enabled_precisions={torch.half}
    )
    input = torch.randn((8, 3, 300, 300)).to("cuda").to(torch.half)
    start = time.time()
    print(trt_model.forward(input))
    end = time.time()
    print(f'Time: {end-start}')


if __name__ == "__main__":
    # export_engine()
    run_engine()
