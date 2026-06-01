"""
pytest 공통 설정.

server/ 자체를 sys.path 에 추가해 `from config import ...`,
`from analyzer ...`, `from models ...` 가 동작하도록 한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
