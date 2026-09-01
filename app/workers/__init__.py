"""Background workers -- currently just the batch-processing orchestrator
(batch_processor.py). The future PySide6 GUI should wrap run_batch() in a
QThread/QRunnable here rather than adding pipeline logic to the UI layer."""
