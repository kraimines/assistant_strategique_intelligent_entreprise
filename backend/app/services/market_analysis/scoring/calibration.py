"""TGATCalibrator — isotonic post-hoc calibration of TGAT raw scores.

Replaces the binary-ish ``signed = (2·s − 1) · sign`` (gnn_predictor.py:569)
with a monotone, calibrated mapping ``T̂(s) ∈ [0,1]`` whose Brier score on
held-out data should beat the raw TGAT logits.

The calibrator uses scikit-learn's ``IsotonicRegression`` when available
(it is already in the project — sklearn is pulled in transitively by other
analysis modules). When sklearn is missing or unfitted we fall back to a
monotone linear mapping so callers never crash.

Persistence: pickle to disk so the Docker image and the worker share the
same calibrator without retraining at every boot.
"""
from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from sklearn.isotonic import IsotonicRegression  # type: ignore
    _HAS_SKLEARN = True
except ImportError:  # pragma: no cover
    IsotonicRegression = None  # type: ignore
    _HAS_SKLEARN = False


class TGATCalibrator:
    """Monotone calibration s_raw → s_calibrated ∈ [0, 1]."""

    def __init__(self) -> None:
        self._model = None  # IsotonicRegression instance once fitted
        self._fallback_slope = 1.0  # used when no model is loaded

    # ── Fitting ──────────────────────────────────────────────────────────────

    def fit_isotonic(self, raw_scores: List[float], realized: List[float]) -> "TGATCalibrator":
        if not _HAS_SKLEARN:
            logger.warning("scikit-learn unavailable — skipping isotonic fit, falling back to identity")
            return self
        if len(raw_scores) != len(realized):
            raise ValueError("raw_scores and realized must be same length")
        if len(raw_scores) < 10:
            logger.warning("Only %d calibration points — fit may be unstable", len(raw_scores))
        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(raw_scores, realized)
        self._model = ir
        logger.info("TGATCalibrator: fit isotonic on %d points", len(raw_scores))
        return self

    # ── Inference ────────────────────────────────────────────────────────────

    def transform(self, raw: float) -> float:
        if self._model is None:
            # Smooth squashing toward [0,1] with no fitted data; preserves order.
            return float(1.0 / (1.0 + math.exp(-self._fallback_slope * raw)))
        try:
            val = float(self._model.predict([float(raw)])[0])
        except Exception:  # noqa: BLE001
            val = float(raw)
        return max(0.0, min(1.0, val))

    def __call__(self, raw: float) -> float:
        return self.transform(raw)

    # ── Persistence ──────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self._model, f)
        logger.info("TGATCalibrator saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "TGATCalibrator":
        path = Path(path)
        c = cls()
        if not path.exists():
            logger.info("TGATCalibrator: no checkpoint at %s — using identity", path)
            return c
        try:
            with path.open("rb") as f:
                c._model = pickle.load(f)
            logger.info("TGATCalibrator: loaded from %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("TGATCalibrator: load failed (%s) — using identity", exc)
        return c

    # ── Utilities ────────────────────────────────────────────────────────────

    @property
    def is_fitted(self) -> bool:
        return self._model is not None

    @staticmethod
    def brier_score(predicted: List[float], actual: List[float]) -> float:
        if not predicted:
            return 0.0
        n = len(predicted)
        return sum((p - a) ** 2 for p, a in zip(predicted, actual)) / n
