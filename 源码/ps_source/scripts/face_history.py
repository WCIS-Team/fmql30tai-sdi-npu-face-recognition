"""Run independent backend quality/history commands, without starting a UI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'model_backend'))
from face_history.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
