"""Ensures the project root is on sys.path so `import app...` works no
matter where pytest is invoked from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
