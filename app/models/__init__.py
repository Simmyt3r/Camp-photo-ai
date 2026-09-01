"""
Domain model placeholder.

Small, single-purpose dataclasses currently live next to the service that
owns them (e.g. DetectedFace in services/face_detection.py, MatchResult
in services/face_matching.py, BatchStats in workers/batch_processor.py)
rather than being centralized here, since each is only used by its
owning service today. This package is reserved for cross-cutting domain
models (e.g. a shared Participant/Photo view model for the future
PySide6 GUI) once more than one part of the app needs the same shape.
"""
