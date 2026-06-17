import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from config_dir import get_config_dir


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


# Eight calibration groups for this device:
# - Z common for all load-cell gravity-direction channels (0,2,4,6 in each block)
# - X common for all load-cell shear-direction channels (1,3,5,7 in each block)
# - Disp common for all displacement channels (8 in each block)
# - AUX0..AUX4 for the auxiliary channel of each block (9 in block n)
CALIBRATION_GROUPS = ["Z", "X", "Disp", "AUX0", "AUX1", "AUX2", "AUX3", "AUX4"]

DEFAULT_CALIBRATION: Dict[str, CalibCoeffs] = {
    key: CalibCoeffs(0.0, 1.0, 0.0) for key in CALIBRATION_GROUPS
}


def _default_json() -> Dict[str, Dict[str, float]]:
    return {key: {"a": 0.0, "b": 1.0, "c": 0.0} for key in CALIBRATION_GROUPS}


class CalibrationStore:
    """Load, save and apply quadratic calibration for the 50ch logger."""

    def __init__(self, filepath: Optional[str] = None):
        if filepath is None:
            filepath = os.path.join(get_config_dir(), "calibration.json")
        self.filepath = filepath
        self._cal: Dict[str, CalibCoeffs] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cal = {}
                for key in CALIBRATION_GROUPS:
                    coeffs = data.get(key, {})
                    self._cal[key] = CalibCoeffs(
                        float(coeffs.get("a", 0.0)),
                        float(coeffs.get("b", 1.0)),
                        float(coeffs.get("c", 0.0)),
                    )
            except Exception:
                self._cal = dict(DEFAULT_CALIBRATION)
                self.save()
        else:
            self._cal = dict(DEFAULT_CALIBRATION)
            self.save()

    def save(self) -> None:
        data = {k: {"a": v.a, "b": v.b, "c": v.c} for k, v in self._cal.items()}
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, key: str) -> CalibCoeffs:
        return self._cal.get(key, CalibCoeffs(0.0, 1.0, 0.0))

    def set(self, key: str, coeffs: CalibCoeffs) -> None:
        self._cal[key] = coeffs
        self.save()

    def set_from_dict(self, data: Dict[str, Dict[str, float]]) -> None:
        for key in CALIBRATION_GROUPS:
            coeffs = data.get(key, {})
            self._cal[key] = CalibCoeffs(
                float(coeffs.get("a", 0.0)),
                float(coeffs.get("b", 1.0)),
                float(coeffs.get("c", 0.0)),
            )
        self.save()

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        return {k: {"a": v.a, "b": v.b, "c": v.c} for k, v in self._cal.items()}

    @staticmethod
    def channel_group(ch_index: int) -> str:
        """Return the calibration group key for a given global channel index."""
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

    def get_channel_coeffs(self, ch_index: int) -> CalibCoeffs:
        return self.get(self.channel_group(ch_index))

    def apply(self, raw_data: List[Optional[float]]) -> List[Optional[float]]:
        return [
            self.get_channel_coeffs(i).apply(raw)
            for i, raw in enumerate(raw_data)
        ]
