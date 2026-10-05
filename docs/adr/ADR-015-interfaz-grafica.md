# ADR-015 — Interfaz gráfica (frontend)

- Estado: **Sustituido por ADR-016** (2026-10-04: GUI PySide6 retirada). Aprobado originalmente (2026-09-27): opción 2, escritorio nativo con PySide6. La prueba de convivencia PySide6 +
  `opencv-python` se hizo el 2026-09-27 y pasó (ver "Resultado de la prueba de convivencia").
- Requisitos afectados: RF-28, §7 (fuera de alcance), RF-34 (stream futuro), SEG-05, SEG-07, SEG-20, SEG-26.

## Contexto
Hechos verificados en el repo el 2026-09-27:

| Hecho | Consecuencia para una GUI |
|---|---|
| El núcleo (procesado, revisión, exportación) está implementado; `process` ya se ejecutó de extremo a extremo (`data/lector.db`, recortes cifrados). | La GUI se apoya en casos de uso que ya funcionan. |
| `data/eval/` vacío: M-01, M-02, M-03 y M-05 nunca se midieron sobre video real con ground truth. OCR `colombia_v1` provisional (M-04 no cumplido). | La implementación del frontend espera a una evaluación E2E (se hace en paralelo al diseño). |
| `application` depende solo de Protocols; `cli` es el composition root (`cli/composition.py`). | Una GUI es un segundo composition root; dominio y pipeline no cambian. |
| `ProcessVideo` no tiene puerto de progreso ni de cancelación (`application/ports.py`). | Cualquier opción necesita un puerto nuevo (progreso por frame/tiempo y cancelación cooperativa). |
| `PlateRepository.list_sightings(status, limit, offset)` pagina y filtra solo por estado. | Buscar por texto/fecha/video exige ampliar el puerto y el adaptador SQLCipher. |
| `block_network()` (`infrastructure/network_guard.py`) parchea `socket.connect`, `connect_ex` y `create_connection`; no toca `bind`/`listen`/`accept`. | Un servidor en loopback funcionaría con la guardia activa, pero SEG-20 no lo contempla: habría que redactarlo. |
| La clave maestra se lee del keyring antes de la guardia (`_prefetch_keys`, `cli/main.py`). | Un proceso de larga vida (GUI) debe leerla una vez al arrancar y mantenerla solo en memoria. |
| `opencv-python==4.14.0.94` trae Qt5 propio (`opencv_python.libs/libQt5*.so.5.15.19`) y `cv2/config-3.py` fija `QT_QPA_PLATFORM_PLUGIN_PATH` y `QT_QPA_FONTDIR` al importarse. | Riesgo de choque con PySide6 (Qt6) en el mismo proceso. Efecto concreto **NO VERIFICADO** (hay que probarlo). |
| La revisión ya es una ventana OpenCV con bucle de `waitKey`. | Existe una "GUI" mínima, pero OpenCV no tiene widgets (listas, tablas, diálogos de archivo). |

Versiones consultadas en el JSON de PyPI el 2026-09-27: PySide6 6.11.2 (LGPL-3.0-only OR GPL-2.0/3.0, Python
>=3.10,<3.15), FastAPI 0.141.1 (MIT), Uvicorn 0.54.0 (BSD-3-Clause), Starlette 1.7.0 (BSD-3-Clause), Jinja2 3.1.6.
Todas compatibles con Python 3.13 y con la licencia AGPL-3.0 del repo (ADR-008).

## Alcance v1 propuesto (común a todas las opciones)
1. Procesar un video local (selector de archivo dentro de `input.allowed_dirs`, perfil) con progreso y cancelación.
2. Listar y filtrar avistamientos (estado, fecha, video, texto) con miniatura del recorte descifrado en memoria.
3. Revisar: confirmar / corregir / rechazar (mismo caso de uso `review_sightings`).
4. Exportar CSV y ver el resultado de purga/retención.
5. Ver métricas de la revisión y el último reporte de `evaluate` si existe.

Fuera de v1: stream en vivo (RF-34), multiusuario, acceso desde otro equipo, entrenamiento desde la GUI.

## Opciones evaluadas
1. **Web local: FastAPI + Uvicorn ligado a 127.0.0.1, HTML/JS servido desde el paquete (sin CDN).**
   - A favor: UI más rica y conocida; se puede abrir en cualquier navegador; separa bien backend (casos de uso) y
     frontend; deja la puerta abierta a RF-34 (el celular enviando video) si algún día se permite red local.
   - En contra: abre un socket de escucha, lo que exige reglas nuevas: bind solo a loopback (nunca `0.0.0.0`), token
     aleatorio por sesión contra otros procesos/usuarios locales y contra CSRF/DNS rebinding (comprobar `Host`), cabeceras
     CSP estrictas, recortes servidos solo desde memoria con `Cache-Control: no-store`, placas enmascaradas en los logs
     de acceso de Uvicorn. Dos pilas (Python + JS) y más superficie de ataque; el navegador puede cachear o guardar
     historial con texto de placa. Nivel F (`strace`) debe distinguir `bind` local de `connect` saliente.
2. **Escritorio nativo: PySide6 (Qt6) en el mismo proceso.**
   - A favor: sin sockets (SEG-20 intacto, la guardia sigue igual); una sola pila Python; widgets completos (tablas,
     diálogos, barras de progreso); los recortes nunca salen del proceso.
   - En contra: posible conflicto con el Qt5 de `opencv-python` (variables `QT_QPA_*` fijadas por `cv2`); mitigaciones
     posibles, a verificar con una prueba real antes de aprobar: importar PySide6 antes que `cv2` y restaurar las variables,
     o sustituir la ventana de revisión OpenCV por widgets Qt y dejar `cv2` solo para procesado de imagen.
     Dependencia grande (~cientos de MB, NO VERIFICADO el tamaño exacto de la wheel). Tests de GUI más difíciles
     (requiere `pytest-qt` o probar solo la capa de presentación).
3. **Ampliar la ventana OpenCV de `lector review`.**
   - A favor: cero dependencias nuevas; ya funciona en este equipo (Qt5/XWayland).
   - En contra: sin widgets: listas, filtros, selección de archivo y progreso habría que dibujarlos a mano con
     `cv2.putText`. No escala más allá de la revisión. Descartable salvo que el objetivo sea solo mejorar la revisión.
4. **UI en terminal (Textual/Rich).** Mencionada por completitud: no muestra imágenes de forma fiable, que es
   imprescindible para revisar recortes. Descartada.

## Decisión
El autor eligió la opción 2 (2026-09-27). Recomendación original:

**Opción 2 (PySide6)** si la GUI es solo para este equipo: mantiene la garantía más fuerte del proyecto (sin red en
runtime) sin reescribir SEG-20. Condición previa: una prueba de convivencia PySide6 + `opencv-python` en este equipo
(un spike descartable) que confirme que la ventana abre con `cv2` importado.
**Opción 1 (web local)** si se quiere usar desde el navegador o preparar RF-34; entonces primero se redactan las reglas
SEG nuevas y se amplía el nivel F.

## Consecuencias (cualquiera que se elija)
- Cambiar RF-28 y §7 en `docs/00-requisitos.md`; sincronizar `ARQUITECTURA.md` (nuevo composition root, capa `gui` o
  `web` que nadie importa, añadirla a `tests/architecture/test_dependency_rule.py`), `reglas-seguridad.md`
  y `docs/02-contratos.md`.
- Puertos nuevos o ampliados antes de la GUI: `ProgressReporter` (progreso + cancelación de `ProcessVideo`) y búsqueda en
  `PlateRepository`, que sirven también a la CLI.

## Resultado de la prueba de convivencia (2026-09-27)
Proyecto desechable fuera del repo (README y `resultados.json` allí). PySide6 6.11.2 + opencv-python 4.14.0.94 + numpy 2.5.3, Python 3.13, sesión Wayland en GNOME.
Cada escenario en un subproceso, en la sesión real y con `QT_QPA_PLATFORM=offscreen`:

| Escenario | Real | Offscreen |
|---|---|---|
| Importar `cv2` y después PySide6 | ok (plataforma `wayland`) | ok |
| Crear la `QApplication` antes de importar `cv2` | ok | ok |
| Importar `cv2`, restaurar `QT_QPA_*` y crear la `QApplication` | ok | ok |
| Ventana Qt6 y `cv2.imshow` abiertas a la vez | ok (la de cv2 por xcb/XWayland) | aborta (SIGABRT): el Qt5 de cv2 no tiene plugin `offscreen` |
| cv2 solo para procesar imagen, sin ventanas cv2 | ok | ok |

Hechos observados: Qt6 no usa el `QT_QPA_PLATFORM_PLUGIN_PATH` que fija `cv2` (resuelve sus plugins en
`PySide6/Qt/plugins`); el orden de importación no importa; sin avisos de fuentes. El motivo por el que Qt6 ignora la
variable queda NO VERIFICADO en la documentación de Qt. Que las ventanas se dibujaran se comprobó solo por ausencia de
errores, no por captura. Tamaño instalado: PySide6 + shiboken6 638 MB (paquete completo; con solo
`PySide6-Essentials` NO VERIFICADO); cv2 + libs 201 MB.

Consecuencias: no hace falta ninguna mitigación de importación. La GUI no debe abrir ventanas
de `cv2` (`imshow`/`namedWindow`): la revisión se reescribe en widgets Qt y `cv2` queda solo para procesar imagen, lo
que además permite probar la GUI con `QT_QPA_PLATFORM=offscreen` en los tests.
