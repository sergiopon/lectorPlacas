from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from legibility_training.common import BOOTSTRAP_ROUNDS, MAX_HIDDEN_LEGIBLE
from legibility_training.dataset import Row
from legibility_training.features import feature_vector
from legibility_training.model import fit, predict_proba


def leave_one_video_out(rows: Sequence[Row]) -> np.ndarray:
    """Evalúa con leave-one-video-out.

    Entrena con todos excepto un grupo de video, predice ese grupo.
    Repite para cada grupo de video distinto (en orden ascendente).

    Returns:
        matriz de probabilidades (N, 3) en el orden de rows
    """
    rows_list = list(rows)
    N = len(rows_list)

    # Encontrar grupos de video únicos en orden ascendente
    video_groups = sorted(set(row.video_group for row in rows_list))

    # Matriz de resultado
    oof = np.zeros((N, 3), dtype=np.float64)

    for hold_group in video_groups:
        # Filas para entrenar (todos excepto hold_group)
        train_indices = [i for i, row in enumerate(rows_list) if row.video_group != hold_group]
        # Filas para predecir (hold_group)
        test_indices = [i for i, row in enumerate(rows_list) if row.video_group == hold_group]

        if not train_indices or not test_indices:
            continue

        # Construir x_train, y_train
        train_rows = [rows_list[i] for i in train_indices]
        train_x = np.array([feature_vector(row) for row in train_rows])

        # Labels: 0=legible, 1=borrosa, 2=no_placa
        class_to_idx = {"legible": 0, "borrosa": 1, "no_placa": 2}
        train_y = np.array([class_to_idx[row.label] for row in train_rows])

        # Entrenar
        model = fit(train_x, train_y)

        # Predecir test
        test_rows = [rows_list[i] for i in test_indices]
        test_x = np.array([feature_vector(row) for row in test_rows])
        test_proba = predict_proba(model, test_x)

        # Guardar en oof
        for pred_idx, orig_idx in enumerate(test_indices):
            oof[orig_idx] = test_proba[pred_idx]

    return oof


def choose_threshold(p_legible: np.ndarray, is_legible: np.ndarray) -> float:
    """Elige el umbral que maximiza detectar legibles sin ocultar demasiadas.

    Busca el mayor t en [0, 0.99] tal que la fracción de legibles con
    p_legible < t sea <= MAX_HIDDEN_LEGIBLE.

    Args:
        p_legible: probabilidad de legible (N,)
        is_legible: etiqueta es legible (N,) booleano

    Returns:
        umbral t
    """
    legible_count = is_legible.sum()
    if legible_count == 0:
        return 0.0

    # Candidatos: 0.00, 0.01, ..., 0.99
    best_t = 0.0
    for k in range(100):
        t = k / 100.0
        hidden = (p_legible[is_legible] < t).sum()
        hidden_frac = hidden / legible_count
        if hidden_frac <= MAX_HIDDEN_LEGIBLE:
            best_t = t

    return best_t


def rates(
    p_legible: np.ndarray,
    is_legible: np.ndarray,
    threshold: float,
) -> tuple[float, float]:
    """Calcula las tasas de legibles e inservibles ocultas.

    Args:
        p_legible: probabilidad de legible (N,)
        is_legible: etiqueta es legible (N,) booleano
        threshold: umbral de decisión

    Returns:
        (legibles_ocultas, inservibles_ocultas) como fracciones
    """
    legible_count = is_legible.sum()
    unusable_count = (~is_legible).sum()

    hidden_legible = (
        (p_legible[is_legible] < threshold).sum() / legible_count if legible_count > 0 else 0.0
    )
    hidden_unusable = (
        (p_legible[~is_legible] < threshold).sum() / unusable_count if unusable_count > 0 else 0.0
    )

    return (float(hidden_legible), float(hidden_unusable))


def baseline_rates(rows: Sequence[Row]) -> tuple[float, float]:
    """Calcula las tasas de la línea base (oculta si num_readings <= 1).

    Returns:
        (legibles_ocultas, inservibles_ocultas)
    """
    rows_list = list(rows)

    # Identificar etiquetas
    class_to_idx = {"legible": 0, "borrosa": 1, "no_placa": 2}
    labels = np.array([class_to_idx[row.label] for row in rows_list])
    is_legible = labels == 0

    # Línea base: oculta si num_readings <= 1
    hidden_mask = np.array([row.num_readings <= 1 for row in rows_list])

    legible_count = is_legible.sum()
    unusable_count = (~is_legible).sum()

    hidden_legible = (hidden_mask[is_legible]).sum() / legible_count if legible_count > 0 else 0.0
    hidden_unusable = (
        (hidden_mask[~is_legible]).sum() / unusable_count if unusable_count > 0 else 0.0
    )

    return (float(hidden_legible), float(hidden_unusable))


def bootstrap_upper(
    p_legible: np.ndarray,
    is_legible: np.ndarray,
    groups: np.ndarray,
    threshold: float,
    seed: int,
) -> float:
    """Calcula el percentil 97.5 de legibles ocultas con bootstrap.

    Remuestrea grupos de video con reemplazo, calcula la tasa en cada uno
    y devuelve el percentil 97.5.

    Args:
        p_legible: probabilidad de legible (N,)
        is_legible: etiqueta es legible (N,) booleano
        groups: grupo de video de cada fila (N,)
        threshold: umbral de decisión
        seed: semilla de RNG

    Returns:
        percentil 97.5 de tasas
    """
    rng = np.random.default_rng(seed)
    unique_groups = np.unique(groups)
    n_groups = len(unique_groups)

    rates_list = []
    for _ in range(BOOTSTRAP_ROUNDS):
        # Remuestrear grupos con reemplazo
        sampled_groups = rng.choice(unique_groups, size=n_groups, replace=True)

        # Concatenar índices de filas para cada grupo muestreado (con repeticiones)
        sample_indices = []
        for group_id in sampled_groups:
            group_indices = np.flatnonzero(groups == group_id)
            sample_indices.extend(group_indices)

        if not sample_indices:
            continue

        sample_indices = np.array(sample_indices)

        # Calcular tasa en esta muestra
        legible_in_sample = is_legible[sample_indices].sum()
        if legible_in_sample == 0:
            # Ignorar muestras sin legibles
            continue

        hidden = (p_legible[sample_indices][is_legible[sample_indices]] < threshold).sum()
        rate = hidden / legible_in_sample
        rates_list.append(rate)

    if not rates_list:
        return 0.0

    return float(np.percentile(rates_list, 97.5))
