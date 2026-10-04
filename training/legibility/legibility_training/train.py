from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime

import numpy as np

from legibility_training.common import (
    CLASSES,
    DATASETS_DIR,
    MIN_PER_CLASS,
    MIN_VIDEO_GROUPS,
    RUNS_DIR,
    LegibilityError,
)
from legibility_training.dataset import near_population, read_export
from legibility_training.evaluate import (
    baseline_rates,
    bootstrap_upper,
    choose_threshold,
    leave_one_video_out,
    rates,
)
from legibility_training.features import FEATURE_NAMES, feature_vector
from legibility_training.model import fit


def main(args: list[str] | None = None) -> int:
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(description="Entrena el filtro de legibilidad")
    parser.add_argument("--export", required=True, help="Directorio de exportación relativo")
    parser.add_argument("--name", required=True, help="Nombre de la ejecución")
    parser.add_argument("--seed", type=int, default=0, help="Semilla para bootstrap")

    parsed = parser.parse_args(args)

    try:
        # Leer dataset
        rows = near_population(read_export(DATASETS_DIR / parsed.export))

        # Contar clases
        class_counts = {cls: 0 for cls in CLASSES}
        for row in rows:
            class_counts[row.label] += 1

        # Contar grupos de video
        video_groups = set(row.video_group for row in rows)
        n_groups = len(video_groups)

        # Verificar datos suficientes
        if (
            any(count < MIN_PER_CLASS for count in class_counts.values())
            or n_groups < MIN_VIDEO_GROUPS
        ):
            raise LegibilityError(
                f"datos insuficientes: "
                f"legible={class_counts['legible']} "
                f"borrosa={class_counts['borrosa']} "
                f"no_placa={class_counts['no_placa']} "
                f"grupos={n_groups}"
            )

        # Características
        X = np.array([feature_vector(row) for row in rows])
        class_to_idx = {"legible": 0, "borrosa": 1, "no_placa": 2}
        y = np.array([class_to_idx[row.label] for row in rows])
        is_legible = y == 0

        # Leave-one-video-out
        oof = leave_one_video_out(rows)
        p_legible = oof[:, 0]

        # Umbral
        t = choose_threshold(p_legible, is_legible)

        # Tasas
        hidden_legible, hidden_unusable = rates(p_legible, is_legible, t)
        baseline_hidden_legible, baseline_hidden_unusable = baseline_rates(rows)

        # Bootstrap upper
        groups = np.array([row.video_group for row in rows])
        upper = bootstrap_upper(p_legible, is_legible, groups, t, parsed.seed)

        # Entrenar modelo final con todas las filas
        final_model = fit(X, y)

        # Validar nombre
        if not re.match(r"^[a-z0-9_]{1,40}$", parsed.name):
            raise LegibilityError("nombre inválido")

        # Crear carpeta de salida
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = RUNS_DIR / parsed.name / timestamp
        output_dir.mkdir(parents=True, mode=0o700)

        # Escribir model.json con permisos 0600
        model_json = {
            "version": 1,
            "features": list(FEATURE_NAMES),
            "classes": list(CLASSES),
            "mean": final_model.mean.tolist(),
            "std": final_model.std.tolist(),
            "weights": final_model.weights.tolist(),
            "bias": final_model.bias.tolist(),
            "threshold": float(t),
        }
        model_path = output_dir / "model.json"
        fd = os.open(str(model_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(model_json, f)

        # Escribir report.json con permisos 0600
        conditions = {
            "c1_hidden_legible_le_5pct": hidden_legible <= 0.05,
            "c2_upper95_le_8pct": upper <= 0.08,
            "c3_hidden_unusable_ge_60pct": hidden_unusable >= 0.60,
            "c4_beats_baseline": (
                hidden_unusable > baseline_hidden_unusable
                and hidden_legible <= max(baseline_hidden_legible, 0.05)
            ),
        }
        verdict = "ACEPTAR" if all(conditions.values()) else "RECHAZAR"

        report_json = {
            "n": {
                "legible": class_counts["legible"],
                "borrosa": class_counts["borrosa"],
                "no_placa": class_counts["no_placa"],
            },
            "video_groups": n_groups,
            "threshold": float(t),
            "hidden_legible": float(hidden_legible),
            "hidden_legible_upper95": float(upper),
            "hidden_unusable": float(hidden_unusable),
            "baseline_hidden_legible": float(baseline_hidden_legible),
            "baseline_hidden_unusable": float(baseline_hidden_unusable),
            "conditions": conditions,
            "verdict": verdict,
        }
        report_path = output_dir / "report.json"
        fd = os.open(str(report_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report_json, f)

        # Imprimir resultados
        print(f"legible={class_counts['legible']}")
        print(f"borrosa={class_counts['borrosa']}")
        print(f"no_placa={class_counts['no_placa']}")
        print(f"threshold={t}")
        print(
            f"c1_hidden_legible_le_5pct={'OK' if conditions['c1_hidden_legible_le_5pct'] else 'NO'}"
        )
        c2_ok = "OK" if conditions["c2_upper95_le_8pct"] else "NO"
        print(f"c2_upper95_le_8pct={c2_ok}")
        c3_ok = "OK" if conditions["c3_hidden_unusable_ge_60pct"] else "NO"
        print(f"c3_hidden_unusable_ge_60pct={c3_ok}")
        c4_ok = "OK" if conditions["c4_beats_baseline"] else "NO"
        print(f"c4_beats_baseline={c4_ok}")
        print(verdict)
        print(output_dir)

        return 0

    except LegibilityError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
