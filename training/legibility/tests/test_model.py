from __future__ import annotations

import numpy as np

from legibility_training.model import fit, predict_proba


def test_fit_separates_classes() -> None:
    """Prueba que el modelo separa bien las clases."""
    rng = np.random.default_rng(0)

    # 300 filas (100 por clase)
    # Clase 0 (legible): primera feature 0.9 ± 0.05, resto ruido
    # Clase 1 (borrosa): primera feature 0.3 ± 0.05, resto ruido
    # Clase 2 (no_placa): primera feature 0.1 ± 0.05, resto ruido

    X_legible = rng.normal(0.9, 0.05, (100, 16))
    X_legible[:, 1:] = rng.normal(0, 1, (100, 15))

    X_borrosa = rng.normal(0.3, 0.05, (100, 16))
    X_borrosa[:, 1:] = rng.normal(0, 1, (100, 15))

    X_no_placa = rng.normal(0.1, 0.05, (100, 16))
    X_no_placa[:, 1:] = rng.normal(0, 1, (100, 15))

    X = np.vstack([X_legible, X_borrosa, X_no_placa])
    y = np.array([0] * 100 + [1] * 100 + [2] * 100)

    # Entrenar
    model = fit(X, y)

    # Predecir
    proba = predict_proba(model, X)

    # Cada fila debe sumar 1
    for row in proba:
        assert abs(row.sum() - 1.0) < 1e-9

    # Predicción correcta en >= 95%
    predictions = np.argmax(proba, axis=1)
    accuracy = (predictions == y).sum() / len(y)
    assert accuracy >= 0.95


def test_constant_feature_has_unit_std() -> None:
    """Prueba que una característica constante tiene std=1.0."""
    X = np.random.default_rng(0).normal(0, 1, (100, 16))
    X[:, 5] = 42.0  # Columna constante
    y = np.array([0] * 50 + [1] * 50)

    model = fit(X, y)

    # std en la posición 5 debe ser 1.0
    assert model.std[5] == 1.0


def test_fit_is_deterministic() -> None:
    """Prueba que fit es determinístico."""
    X = np.random.default_rng(0).normal(0, 1, (100, 16))
    y = np.array([0] * 50 + [1] * 50)

    model1 = fit(X, y)
    model2 = fit(X, y)

    assert np.array_equal(model1.weights, model2.weights)
    assert np.array_equal(model1.bias, model2.bias)
