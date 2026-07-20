"""Time-safe probability calibration helpers for match result probabilities."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.metrics import log_loss


RESULT_CLASSES = np.asarray([-1, 0, 1], dtype=int)


def temperature_scale_matrix(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 3:
        raise ValueError("probabilities must have shape (n_samples, 3).")
    temperature = float(temperature)
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be a finite value greater than 0.")

    logits = np.log(np.clip(probabilities, 1e-15, 1.0)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    scaled = np.exp(logits)
    return scaled / scaled.sum(axis=1, keepdims=True)


def fit_temperature(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Fit one temperature by minimizing multiclass log loss."""

    probabilities = np.asarray(probabilities, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if len(probabilities) != len(labels) or len(labels) == 0:
        raise ValueError("probabilities and labels must have the same non-zero length.")

    def objective(log_temperature: float) -> float:
        temperature = float(np.exp(log_temperature))
        scaled = temperature_scale_matrix(probabilities, temperature)
        return float(log_loss(labels, scaled, labels=RESULT_CLASSES))

    result = minimize_scalar(
        objective,
        bounds=(float(np.log(0.25)), float(np.log(4.0))),
        method="bounded",
        options={"xatol": 1e-6},
    )
    if not result.success:
        raise RuntimeError(f"temperature optimization failed: {result.message}")
    return float(np.exp(result.x))
