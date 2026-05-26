"""Shared pytest setup.

Adds the agent directory to ``sys.path`` so tests can import
``rgv_lead_scraper.auth.*`` even without ``pip install -e .`` having
been run. CI is expected to install the package, but local edit-test
loops shouldn't require it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT / "src", _REPO_ROOT / "agents"):
    spath = str(_p)
    if spath not in sys.path:
        sys.path.insert(0, spath)
