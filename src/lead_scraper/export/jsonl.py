from __future__ import annotations

import json
from pathlib import Path

from lead_scraper.models import Lead, lead_to_dict


class JsonlExporter:
    def __init__(self, out_path: str):
        self._out_path = Path(out_path)

    def export(self, leads: list[Lead]) -> str:
        self._out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._out_path.open("w", encoding="utf-8") as f:
            for lead in leads:
                f.write(json.dumps(lead_to_dict(lead), ensure_ascii=False) + "\n")
        return str(self._out_path)
