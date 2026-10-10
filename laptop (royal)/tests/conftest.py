"""Put the working pose controller on the import path for these tests."""

import sys
from pathlib import Path

_CONTROLLER_DIR = Path(__file__).resolve().parents[1]
if str(_CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROLLER_DIR))
