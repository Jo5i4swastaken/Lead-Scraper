from __future__ import annotations

import json
from pathlib import Path

from lead_scraper.export.identity import lead_identity
from lead_scraper.export.schema import lead_to_export_dict
from lead_scraper.models import Lead


class JsonlExporter:
    def __init__(self, out_path: str, *, incremental: bool = True):
        self._out_path = Path(out_path)
        self._incremental = incremental

    def export(self, leads: list[Lead]) -> str:
        self._out_path.parent.mkdir(parents=True, exist_ok=True)

        existing_ids: set[str] = set()
        if self._incremental and self._out_path.exists():
            with self._out_path.open("r", encoding="utf-8") as f:
                for line in f:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        obj = json.loads(text)
                    except Exception:
                        continue
                    key = str(obj.get("lead_id") or "").strip()
                    if key:
                        existing_ids.add(key)

        seen_this_run: set[str] = set()
        mode = "a" if (self._incremental and self._out_path.exists()) else "w"
        with self._out_path.open(mode, encoding="utf-8") as f:
            for lead in leads:
                key = lead_identity(lead)
                if key in existing_ids or key in seen_this_run:
                    continue
                seen_this_run.add(key)
                f.write(json.dumps(lead_to_export_dict(lead), ensure_ascii=False) + "\n")

        return str(self._out_path)

