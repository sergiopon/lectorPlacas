# ADR-008 — Licencia AGPL-3.0 (Ultralytics)

- Estado: Aceptado (2026-09-24)
- Requisitos: RNF-16

## Contexto
Ultralytics (YOLO26, entrenamiento y exportación) se distribuye bajo AGPL-3.0 o licencia Enterprise
(https://www.ultralytics.com/license). AGPL-3.0 obliga a publicar el código fuente del proyecto que
lo usa, incluidos modelos entrenados y uso por red. El usuario publicará el repositorio como
portafolio personal/académico (confirmado 2026-09-24).

## Opciones evaluadas
1. **Publicar todo bajo AGPL-3.0.**
2. Licencia Enterprise: precio no público; innecesaria para uso personal.
3. Evitar Ultralytics (RF-DETR / YOLOX / D-FINE, Apache-2.0): pierde el ecosistema de entrenamiento
   y exportación a móvil de YOLO26.

## Decisión
El repositorio se licencia **AGPL-3.0-only**. `LICENSE` contiene el texto oficial descargado de
https://www.gnu.org/licenses/agpl-3.0.txt. Los pesos fine-tuneados derivados de YOLO26 se consideran
cubiertos por AGPL-3.0. Las dependencias con licencia permisiva (MIT, Apache-2.0, BSD) son compatibles.
Los datasets CC BY 4.0 requieren atribución en `docs/datasets/ATRIBUCIONES.md` (Fase 5).

## Consecuencias
- (+) Uso libre de Ultralytics para el portafolio.
- (−) Cualquier uso comercial cerrado futuro requiere licencia Enterprise o cambiar de detector
  (el puerto `VehicleDetector`/`PlateDetector` lo permite sin tocar el dominio).
