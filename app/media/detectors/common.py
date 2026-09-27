"""What every local model needs: where its files are, and a CPU session to run it."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps


def model_path(directory: str, *parts: str) -> Path | None:
    """The file, when it has been downloaded; None otherwise."""
    path = Path(directory, *parts)
    return path if path.is_file() and path.stat().st_size > 0 else None


def onnx_session(path: Path, *, threads: int) -> Any:
    """A CPU inference session. onnxruntime ships with fastembed, so it is always here."""
    import onnxruntime as ort  # type: ignore[import-untyped]

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    # The memory arena grows to the largest input ever seen and never gives it back;
    # on a server holding several models that is memory spent on nothing.
    options.enable_cpu_mem_arena = False
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def rgb(data: bytes) -> Image.Image:
    """The picture as upright RGB: phones store rotation in EXIF, not in the pixels."""
    with Image.open(io.BytesIO(data)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def normalised(
    image: Image.Image, *, mean: tuple[float, ...], std: tuple[float, ...]
) -> np.ndarray:
    """HWC uint8 to a 1xCxHxW float32 tensor, scaled to 0-1 and normalised."""
    scaled = np.asarray(image, dtype=np.float32) / np.float32(255.0)
    centred = (scaled - np.array(mean, dtype=np.float32)) / np.array(std, dtype=np.float32)
    return centred.transpose(2, 0, 1)[None, ...].astype(np.float32)
