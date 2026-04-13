"""Add tools/ to sys.path so tests can import mempatterns, etc."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
