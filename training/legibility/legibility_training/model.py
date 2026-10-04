from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

L2: Final[float] = 1.0
LEARNING_RATE: Final[float] = 0.1
ITERATIONS: Final[int] = 2000


@dataclass(frozen=True, slots=True)
class LogisticModel:
    """Modelo de regresión logística multinomial."""

    mean: np.ndarray  # (16,)
    std: np.ndarray  # (16,)
    weights: np.ndarray  # (3, 16)
    bias: np.ndarray  # (3,)


def fit(x: np.ndarray, y: np.ndarray) -> LogisticModel:
    """Entrena un modelo de regresión logística multinomial.

    Args:
        x: matriz de características (N, 16) float64
        y: etiquetas (N,) enteros 0-2

    Returns:
        LogisticModel entrenado
    """
    N = x.shape[0]

    # Normalización
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std = np.where(std == 0.0, 1.0, std)
    z = (x - mean) / std

    # Inicialización
    W = np.zeros((3, 16), dtype=np.float64)
    b = np.zeros(3, dtype=np.float64)

    # One-hot encoding de y
    Y = np.zeros((N, 3), dtype=np.float64)
    Y[np.arange(N), y] = 1.0

    # Entrenamiento
    for _ in range(ITERATIONS):
        # Forward
        logits = z @ W.T + b
        # Softmax (restando máximo por fila para estabilidad)
        logits_shifted = logits - logits.max(axis=1, keepdims=True)
        exp_logits = np.exp(logits_shifted)
        P = exp_logits / exp_logits.sum(axis=1, keepdims=True)

        # Gradientes
        G = (P - Y) / N
        W -= LEARNING_RATE * (G.T @ z + L2 * W / N)
        b -= LEARNING_RATE * G.sum(axis=0)

    return LogisticModel(mean=mean, std=std, weights=W, bias=b)


def predict_proba(model: LogisticModel, x: np.ndarray) -> np.ndarray:
    """Predice probabilidades para cada clase.

    Args:
        model: LogisticModel entrenado
        x: matriz de características (N, 16) float64

    Returns:
        matriz de probabilidades (N, 3)
    """
    z = (x - model.mean) / model.std
    logits = z @ model.weights.T + model.bias
    # Softmax
    logits_shifted = logits - logits.max(axis=1, keepdims=True)
    exp_logits = np.exp(logits_shifted)
    return exp_logits / exp_logits.sum(axis=1, keepdims=True)
