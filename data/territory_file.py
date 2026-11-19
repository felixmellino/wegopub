"""Reads the shared territory outlines from data/territories.geojson (R-T01).

The file is the single source of truth for territories. The database's
`territories` table is only a copy, kept in sync by shared.get_territories(),
so that drink entries can reference a territory id.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.models import Territory
from core.territories import parse_territories

TERRITORY_FILE = Path(__file__).resolve().parent / "territories.geojson"


def territory_file_version(path: Path = TERRITORY_FILE) -> str:
    """A fingerprint of the file's contents. It changes whenever anyone edits
    the file, so the app knows to load and copy the territories again."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_territories(path: Path = TERRITORY_FILE) -> list[Territory]:
    with open(path, encoding="utf-8") as f:
        return parse_territories(json.load(f))
