# ADR-005 — Persistencia y cifrado

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-21..RF-26, RF-30, RNF-09..RNF-12, RNF-15 (Ley 1581 de 2012)

## Contexto
Las placas son dato personal. El usuario exige cifrado de BD y recortes, clave en el llavero del
SO, un solo operador local y retención 30 días (recortes) / 90 días (registros).

## Opciones evaluadas
- SQLite sin cifrar + disco cifrado (LUKS): no protege si se copia el archivo.
- **SQLCipher vía `sqlcipher3` 0.6.2** (MIT, wheels manylinux cp313 autocontenidas, módulo
  `sqlcipher3.dbapi2`, compatible con la API de `sqlite3`). `pysqlcipher3` está abandonado.
- Cifrado a nivel de columna: complica índices y consultas.
- Clave: keyring del SO (elegida), passphrase por consola, variable de entorno.

## Decisión
1. **BD:** SQLCipher con clave cruda de 32 bytes: `PRAGMA key = "x'<64 hex>'"` (formato "Raw Key
   Data" de https://www.zetetic.net/sqlcipher/sqlcipher-api/). La clave hex se valida con
   `^[0-9a-f]{64}$` antes de interpolarla (única excepción permitida a "solo consultas
   parametrizadas", porque `PRAGMA` no admite parámetros).
2. **Recortes:** PNG en memoria → AES-256-GCM (`cryptography` 50.0.1, `AESGCM`), nonce aleatorio de
   12 bytes, AAD = `crop_ref`. Archivo `data/crops/<ref[0:2]>/<ref>.bin` = `nonce || ciphertext`.
3. **Claves:** clave maestra aleatoria de 32 bytes (`os.urandom`) guardada en hex en el keyring
   (`keyring` 25.7.0, servicio `lector-placas`, usuario `master-key`; backend SecretService en Fedora).
   Subclaves con HKDF-SHA256: `info=b"lector-placas/sqlcipher/v1"` y `info=b"lector-placas/crops/v1"`.
4. **Permisos:** directorios de datos 0700, archivos 0600. Escritura atómica (temporal + `os.replace`).
5. **Minimización:** no se guarda la ruta ni el nombre del video, solo su SHA-256 y metadatos técnicos.
6. **Retención:** purga automática al iniciar cada comando que abre la BD + comando `purge`.

## Consecuencias
- (+) Archivos ilegibles sin la clave; la clave nunca toca el disco del proyecto.
- (−) Sin sesión gráfica/SecretService desbloqueado el sistema no arranca (`KeyUnavailableError`).
- (−) Perder el keyring = perder los datos (aceptado: son datos de retención corta).
- Los tests usan un `KeyProvider` falso con clave sintética.

## Actualización 2026-09-26
Por decisión del usuario, las lecturas revisadas (`confirmed`/`corrected`) pueden exportarse descifradas para reentrenar
el OCR (`lector dataset export-reviewed`, spec 035): excepción controlada a SEG-07, con retención propia
`retention.training_days` (180 días) aplicada por la purga, permisos 0600/0700 y registro en `audit_log`.

## Actualización 2026-10-03
La excepción a SEG-07 se amplía a `lector dataset export-legibility` (spec 055): exporta los recortes de los
avistamientos con estado final (`confirmed`, `corrected`, `illegible`, `rejected`) con su clase de legibilidad y las
métricas del consolidador, **sin texto de placa ni hash de video**, a `training/legibility/datasets/own/`. Misma
retención (`training_days`), permisos y auditoría. Sirve para entrenar el filtro de legibilidad (docs/historial/08 §2).

## Actualización 2026-10-03 (spec 074)
Dentro de un contenedor no hay Secret Service. Si `LECTOR_KEY_FILE` contiene una ruta absoluta, la clave se lee de ese
archivo (64 hex y salto de línea opcional, archivo regular del usuario del proceso, sin permisos de grupo ni otros).
`lector key export-file <ruta>` copia la clave del keyring (mismos datos dentro y fuera de Docker) y
`lector key init-file <ruta>` genera una nueva. El archivo se monta como Docker secret (spec 075) y nunca entra en el
repo ni en la imagen.
