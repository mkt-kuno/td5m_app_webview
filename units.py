import json
import os
from typing import Dict, Optional

from config_dir import get_config_dir


# Unit groups matching calibration groups
UNIT_GROUPS = ["Z", "X", "Disp", "AUX0", "AUX1", "AUX2", "AUX3", "AUX4"]

# Fixed units for Z/X (force) and Disp (displacement)
DEFAULT_UNITS: Dict[str, str] = {
    "Z": "N",
    "X": "N",
    "Disp": "mm",
    "AUX0": "",
    "AUX1": "",
    "AUX2": "",
    "AUX3": "",
    "AUX4": "",
}

# Common units for AUX combobox
COMMON_UNITS = ["", "N", "kN", "mm", "μm", "m", "°", "%", "V", "A", "Ω", "Hz", "Pa", "kPa", "MPa"]


class UnitStore:
    """Load, save and provide units for each channel group."""

    def __init__(self, filepath: Optional[str] = None):
        if filepath is None:
            filepath = os.path.join(get_config_dir(), "units.json")
        self.filepath = filepath
        self._units: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._units = {}
                for key in UNIT_GROUPS:
                    self._units[key] = str(data.get(key, DEFAULT_UNITS[key]))
            except Exception:
                self._units = dict(DEFAULT_UNITS)
                self.save()
        else:
            self._units = dict(DEFAULT_UNITS)
            self.save()

    def save(self) -> None:
        data = {k: self._units.get(k, DEFAULT_UNITS[k]) for k in UNIT_GROUPS}
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, key: str) -> str:
        return self._units.get(key, DEFAULT_UNITS.get(key, ""))

    def set(self, key: str, unit: str) -> None:
        if key in UNIT_GROUPS:
            self._units[key] = unit
            self.save()

    def set_from_dict(self, data: Dict[str, str]) -> None:
        for key in UNIT_GROUPS:
            if key in data:
                self._units[key] = str(data[key])
        self.save()

    def to_dict(self) -> Dict[str, str]:
        return {k: self._units.get(k, DEFAULT_UNITS[k]) for k in UNIT_GROUPS}

    @staticmethod
    def channel_group(ch_index: int) -> str:
        """Return the unit group key for a given global channel index."""
        block = ch_index // 10
        pos = ch_index % 10
        if pos in (0, 2, 4, 6):
            return "Z"
        if pos in (1, 3, 5, 7):
            return "X"
        if pos == 8:
            return "Disp"
        if pos == 9:
            return f"AUX{block}"
        return "Z"

    def get_channel_unit(self, ch_index: int) -> str:
        return self.get(self.channel_group(ch_index))
