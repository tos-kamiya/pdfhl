import os
import sys

# Ensure the src/ directory is on sys.path for imports like `from pdfhl import ...`
_ROOT = os.path.dirname(os.path.dirname(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
