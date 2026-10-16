import base64
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: python tools/encode_private_key.py path/to/CampPhotoAI_PILOT_PRIVATE_KEY.pem")
path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"Private key not found: {path}")
print(base64.b64encode(path.read_bytes()).decode("ascii"))
