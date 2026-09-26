# ADR-012 — Sin red en runtime y registro de modelos verificado

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-32, RF-33, RNF-07, RNF-08

## Contexto
`fast-plate-ocr` y `open-image-models` descargan modelos de GitHub si no se les da ruta local;
Ultralytics comprueba conectividad y auto-instala paquetes (`YOLO_AUTOINSTALL`). El requisito es
cero llamadas de red durante el procesamiento y modelos verificados por SHA-256.

## Decisión
1. `config/models.yaml` (versionado) lista cada modelo: `model_id`, `filename`, `url` (o `null` si es
   producido localmente), `sha256`, `size_bytes`, `license`, `source`.
2. Comando explícito `lector models fetch`: única operación con red. Solo URLs `https://github.com/`;
   descarga a un temporal, verifica tamaño y SHA-256 **antes** de moverlo a `models/<model_id>/<filename>`.
3. Runtime: `ManifestModelRegistry.verified_path(model_id)` recalcula el SHA-256 en cada carga; si no
   coincide → `ModelIntegrityError` y el proceso termina (código 4). Los adaptadores reciben rutas
   locales (`onnx_model_path`, `plate_config_path`, `model_path`), nunca nombres de hub.
4. Guardia de red: todos los comandos salvo `models fetch` llaman a `block_network()` al inicio, que
   reemplaza `socket.socket.connect`/`connect_ex` y `socket.create_connection` por funciones que
   lanzan `NetworkAccessError`.
5. En `training/`, las variables `YOLO_OFFLINE=True` y `YOLO_AUTOINSTALL=False` se exportan en los
   scripts salvo en el paso de descarga inicial de `yolo26n.pt`.

Hashes fijados (calculados el 2026-09-24 sobre las URLs oficiales):
| model_id | archivo | SHA-256 | bytes |
|---|---|---|---|
| `oim-yolo-v9-t-384-plates` | yolo-v9-t-384-license-plates-end2end.onnx | 888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8 | 7771218 |
| `fpo-cct-xs-v2-global` | cct_xs_v2_global.onnx | 8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44 | 3344292 |
| `fpo-cct-xs-v2-global-config` | cct_xs_v2_global_plate_config.yaml | 0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6 | 1725 |
| `fpo-cct-xs-v2-global-keras` (solo training) | cct_xs_v2_global.keras | 0716717772b1f8d25b3c227e1e65e7f42e63900ec017059b4a32155488735ffd | 10865307 |
| `fpo-cct-xs-v2-global-model-config` (solo training) | cct_xs_v2_global_model_config.yaml | e85d14b22bc6e68652375fa0d78e8e0ae5f69d4cca948962ccd77a79161c0358 | 1351 |
| `ul-yolo26n-coco-pt` (solo training) | yolo26n.pt | 9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef | 5544453 |

## Consecuencias
- (+) Integridad y aislamiento de red verificables por tests.
- (−) El modelo exportado localmente (`yolo26n-coco`) obtiene su hash al exportarse (spec 030) y debe
  registrarse en `config/models.yaml` antes de usarse (trust-on-first-export, documentado).
- (−) La guardia bloquea también los sockets Unix, incluido D-Bus: la clave maestra se lee del keyring antes de
  `block_network()` y queda en memoria (corrección 2026-09-26, spec 028).
