"""Numpy array / bytes <-> QPixmap conversion helpers for the GUI."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap


def numpy_to_qpixmap(image_bgr: np.ndarray) -> QPixmap:
    """Converts an OpenCV-style BGR numpy array to a QPixmap."""
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    qimage = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
    # QImage wraps the numpy buffer without copying it by default --
    # .copy() detaches the QImage from that buffer's memory so the
    # resulting pixmap stays valid after `rgb` goes out of scope here.
    return QPixmap.fromImage(qimage.copy())


def bytes_to_qpixmap(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return pixmap


def crop_with_padding(
    image_bgr: np.ndarray, bbox: tuple[float, float, float, float], padding_ratio: float = 0.3
) -> np.ndarray:
    """Crops a face region out of a full photo with some context padding
    around the detected bounding box, clamped to the image bounds."""
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    pad_x, pad_y = bw * padding_ratio, bh * padding_ratio
    x1 = max(0, int(x1 - pad_x))
    y1 = max(0, int(y1 - pad_y))
    x2 = min(w, int(x2 + pad_x))
    y2 = min(h, int(y2 + pad_y))
    if x2 <= x1 or y2 <= y1:
        return image_bgr
    return image_bgr[y1:y2, x1:x2]
