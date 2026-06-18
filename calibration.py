import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config_dir import get_config_dir


NUM_CHANNELS = 50
CHANNEL_KEYS = [f"{i:02d}" for i in range(NUM_CHANNELS)]

# Eight calibration groups; Z/X/Disp share a,b across all channels of their type.
# AUX0..AUX4 are per-block auxiliary channels (pos 9 in each block).
CALIBRATION_GROUPS = ["Z", "X", "Disp", "AUX0", "AUX1", "AUX2", "AUX3", "AUX4"]


def _build_group_channels() -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = {g: [] for g in CALIBRATION_GROUPS}
    for ch in range(NUM_CHANNELS):
        block = ch // 10
        pos = ch % 10
        if pos in (0, 2, 4, 6):
            g = "Z"
        elif pos in (1, 3, 5, 7):
            g = "X"
        elif pos == 8:
            g = "Disp"
        else:
            g = f"AUX{block}"
        groups[g].append(ch)
    return groups


GROUP_CHANNELS: Dict[str, List[int]] = _build_group_channels()


@dataclass
class CalibCoeffs:
    """Quadratic calibration coefficients: physical = a*raw^2 + b*raw + c"""
    a: float
    b: float
    c: float

    def apply(self, raw: Optional[float]) -> Optional[float]:
        if raw is None:
            return None
        return self.a * raw * raw + self.b * raw + self.c


class CalibrationStore:
    """Per-channel calibration storage.

    a,b are shared within Z/X/Disp groups (changing one updates all channels
    of that type). c (Tare offset) is per-channel.
    JSON format: {"00": {a,b,c}, ..., "49": {a,b,c}, "type": "Calibration"}
    """

    def __init__(self, filepath: Optional[str] = None):
        if filepath is None:
            filepath = os.path.join(get_config_dir(), "calibration.json")
        self.filepath = filepath
        self._cal: Dict[str, CalibCoeffs] = {}
        self.load()

    def _default_cal(self) -> Dict[str, CalibCoeffs]:
        return {k: CalibCoeffs(0.0, 1.0, 0.0) for k in CHANNEL_KEYS}

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Detect old named-group format and migrate
                if any(k in data for k in CALIBRATION_GROUPS):
                    self._cal = self._migrate_from_old(data)
                    self.save()
                else:
                    self._cal = {}
                    for k in CHANNEL_KEYS:
                        ch_data = data.get(k, {})
                        self._cal[k] = CalibCoeffs(
                            float(ch_data.get("a", 0.0)),
                            float(ch_data.get("b", 1.0)),
                            float(ch_data.get("c", 0.0)),
                        )
            except Exception:
                self._cal = self._default_cal()
                self.save()
        else:
            self._cal = self._default_cal()
            self.save()

    def _migrate_from_old(self, data: dict) -> Dict[str, CalibCoeffs]:
        result = {}
        for ch in range(NUM_CHANNELS):
            group = self.channel_group(ch)
            old = data.get(group, {})
            result[f"{ch:02d}"] = CalibCoeffs(
                float(old.get("a", 0.0)),
                float(old.get("b", 1.0)),
                float(old.get("c", 0.0)),
            )
        return result

    def save(self) -> None:
        data: Dict = {k: {"a": v.a, "b": v.b, "c": v.c} for k, v in self._cal.items()}
        data["type"] = "Calibration"
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def channel_group(ch_index: int) -> str:
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

    def get_group_ab(self, group: str) -> Tuple[float, float]:
        """Return the shared a,b for a group (read from its first channel)."""
        channels = GROUP_CHANNELS.get(group, [])
        if channels:
            c = self._cal.get(f"{channels[0]:02d}", CalibCoeffs(0.0, 1.0, 0.0))
            return c.a, c.b
        return 0.0, 1.0

    def set_group_ab(self, group: str, a: float, b: float) -> None:
        """Update a,b for every channel in the group (c unchanged)."""
        for ch in GROUP_CHANNELS.get(group, []):
            key = f"{ch:02d}"
            old = self._cal.get(key, CalibCoeffs(0.0, 1.0, 0.0))
            self._cal[key] = CalibCoeffs(a, b, old.c)

    def set_from_groups(self, group_data: Dict[str, Dict[str, float]]) -> None:
        """Update a,b from group-keyed dict {"Z":{a,b}, ...}. c is unchanged."""
        for group in CALIBRATION_GROUPS:
            if group in group_data:
                a = float(group_data[group].get("a", 0.0))
                b = float(group_data[group].get("b", 1.0))
                self.set_group_ab(group, a, b)
        self.save()

    def get_channel_c(self, ch_index: int) -> float:
        return self._cal.get(f"{ch_index:02d}", CalibCoeffs(0.0, 1.0, 0.0)).c

    def set_channel_c(self, ch_index: int, c: float) -> None:
        key = f"{ch_index:02d}"
        old = self._cal.get(key, CalibCoeffs(0.0, 1.0, 0.0))
        self._cal[key] = CalibCoeffs(old.a, old.b, c)
        self.save()

    def get_channel_coeffs(self, ch_index: int) -> CalibCoeffs:
        return self._cal.get(f"{ch_index:02d}", CalibCoeffs(0.0, 1.0, 0.0))

    def groups_dict(self) -> Dict[str, Dict[str, float]]:
        """Return group-level a,b for UI display."""
        return {g: {"a": a, "b": b} for g in CALIBRATION_GROUPS
                for a, b in [self.get_group_ab(g)]}

    def to_dict(self) -> Dict:
        """Return full per-channel dict for JSON export."""
        data: Dict = {k: {"a": v.a, "b": v.b, "c": v.c} for k, v in self._cal.items()}
        data["type"] = "Calibration"
        return data

    def apply(self, raw_data: List[Optional[float]]) -> List[Optional[float]]:
        return [
            self.get_channel_coeffs(i).apply(raw)
            for i, raw in enumerate(raw_data)
        ]
