# Atribuciones de los datasets públicos

Datasets de Roboflow Universe con los que se entrenaron los modelos propios publicados en el Release `models-v1`
(`yolo26n-plates` y `fpo-cct-xs-v2-colombia`). Se descargan con `lector dataset prepare` (API REST de Roboflow;
lista en `config/datasets.yaml`). Las versiones y fechas de exportación se comprobaron en los archivos
descargados (`data.yaml` y `README.roboflow.txt`).

| Dataset | Autor en Roboflow | URL | Licencia | Versión | Exportado | Uso |
|---|---|---|---|---|---|---|
| Placas_Motos_Carros | reimerjsuarez | https://universe.roboflow.com/reimerjsuarez/placas_motos_carros | CC BY 4.0 | 3 | 2026-09-27 | Detector de placas |
| motos-placas | placas-sn7fb | https://universe.roboflow.com/placas-sn7fb/motos-placas | CC BY 4.0 | 1 | 2026-07-22 (fecha de la exportación de Roboflow) | Detector de placas (motos; origen colombiano NO VERIFICADO) |
| OCR Placas Colombia | ia-xgdnt | https://universe.roboflow.com/ia-xgdnt/ocr-placas-colombia-etll5 | CC BY 4.0 (según su página en Roboflow; el archivo descargado no incluye la licencia) | 1 del fork propio `sergio-ponce-asprilla/ocr-placas-colombia-etll5-lwpkc`, porque el original no tiene versiones generadas | 2026-09-27 | OCR (recortes de caracteres → placas) |

Excluidos (no se usaron para entrenar): `usco-thj9e/placas-colombia-ixdpr` (son recortes de placa, no escenas) y
`licenseplates-gk27i/placas-colombianas` (clases corruptas). Motivos en `config/datasets.yaml`.

## Modelos base

| Modelo | Autor | Licencia | Uso |
|---|---|---|---|
| YOLO26n (COCO) | Ultralytics | AGPL-3.0 | Detector de vehículos (`yolo26n-coco`) y base de `yolo26n-plates` |
| cct-xs-v2-global (fast-plate-ocr) | ankandrew | MIT | Base del OCR `fpo-cct-xs-v2-colombia` |
| yolo-v9-t-384 license plates (open-image-models) | ankandrew | MIT (licencia del repositorio; la de los pesos NO VERIFICADA) | Detector de placas por defecto (no se redistribuye: se descarga de su Release original) |

Los datasets CC BY 4.0 exigen atribución; esta tabla se publica con el repositorio y se enlaza desde el Release.
