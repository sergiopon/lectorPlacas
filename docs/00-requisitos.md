# 00 — Requisitos

> **Fase 1** del desarrollo spec-driven de `lectorPlacas`.
> Documento de requisitos. No contiene código ni decisiones de implementación (esas se toman en Fase 2).
> Toda cifra o dato que no provenga de una fuente listada aquí se marca **PENDIENTE DE VALIDAR**.

## 1. Propósito y alcance

Definir qué debe hacer `lectorPlacas`, un sistema ALPR (reconocimiento automático de placas) local
escrito en Python. La entrada es un archivo de video de tráfico en Colombia; la salida son
avistamientos de placas persistidos en una base de datos cifrada, con timestamp relativo, confianza,
tipo de vehículo y recorte cifrado de la placa. El uso es personal/académico, en una sola máquina,
operado por una sola persona. Este documento fija el alcance de la v1, los criterios de aceptación y
lo que queda explícitamente fuera.

## 2. Contexto y supuestos

| # | Supuesto | Estado |
|---|---|---|
| C-01 | El sistema corre en la PC del usuario: Fedora 44, GPU NVIDIA RTX 5050 8 GB VRAM, Blackwell sm_120, driver 610.57. | Verificado (entorno del usuario) |
| C-02 | PyTorch 2.14.0: los builds cu128 fueron retirados desde PyTorch 2.12; los builds actuales son cu126, cu130 y cu132. | Verificado — https://dev-discuss.pytorch.org/t/introducing-cuda-13-2-and-deprecating-cuda-12-8-release-2-12/3337 |
| C-03 | cu126 no incluye sm_120; se requiere build CUDA ≥ 12.8 con soporte sm_120 → **cu130**. | Verificado (misma fuente que C-02) |
| C-04 | Todos los modelos cargados simultáneamente deben caber en 8 GB de VRAM. | Confirmado por usuario |
| C-05 | Ultralytics es AGPL-3.0 (https://www.ultralytics.com/license) y su uso es aceptable porque el repo será público. | Confirmado por usuario + verificado (licencia) |
| C-06 | El OCR preentrenado candidato (fast-plate-ocr 1.1.0, MIT) no entrenó con Colombia: en LatAm solo Argentina, Brasil y México → requiere fine-tuning. | Verificado — https://github.com/ankandrew/fast-plate-ocr |
| C-07 | El pipeline previsto es: decodificación → detección de vehículos → detección de placas → tracking → OCR → consolidación por track (votación + validación de formato + corrección posicional) → persistencia. El pipeline definitivo se decide en Fase 2. | Confirmado por usuario (contexto) |
| C-08 | El desarrollo es spec-driven: un LLM externo (DeepSeek) implementa las specs y **nunca** recibe datos reales. | Confirmado por usuario |
| C-09 | La PC de referencia para medir rendimiento es la del usuario (RTX 5050); el sistema también debe poder correr en otras máquinas, por lo que los modelos deben ser pequeños y portables. | Confirmado por usuario |
| C-10 | El archivo de resultados de evaluación y su formato se definen en `docs/04-evaluacion.md` (Fase 5). | Decisión de proceso |
| C-11 | Cantidad de dato colombiano público disponible (~1.800 imágenes de detección, 926 con cajas por carácter, pocas motos, ninguna con transcripción de texto). Posibles duplicados entre proyectos y licencias declaradas por quien sube los datos: NO VERIFICADO. | Verificado — Roboflow Universe, conteos leídos el 2026-09-24: placas-colombianas (1.770, CC BY 4.0) https://universe.roboflow.com/licenseplates-gk27i/placas-colombianas ; usco (1.106, MIT) https://universe.roboflow.com/usco-thj9e/placas-colombia-ixdpr ; OCR Placas Colombia (926, cajas por carácter, CC BY 4.0) https://universe.roboflow.com/ia-xgdnt/ocr-placas-colombia-etll5 ; Placas_Motos_Carros (469) https://universe.roboflow.com/reimerjsuarez/placas_motos_carros ; motos-placas (264) https://universe.roboflow.com/placas-sn7fb/motos-placas |

## 3. Actores

| Actor | Descripción | Acceso a datos |
|---|---|---|
| Operador local | Única persona que ejecuta el pipeline, revisa lecturas dudosas y purga datos. Usa la CLI. | Total (es el dueño de la máquina y de los datos). |
| Implementador externo (DeepSeek) | LLM que implementa las specs de cada fase. Solo ve especificaciones, código y datos sintéticos. | **Ninguno** sobre datos reales: no recibe videos, recortes, placas ni la clave de cifrado. |

## 4. Requisitos funcionales

Prioridad: MUST (obligatorio en v1) / SHOULD (deseable) / COULD (opcional).
Origen: número del requisito confirmado por el usuario en el brief de esta fase.

| ID | Descripción verificable | Prioridad | Origen |
|---|---|---|---|
| RF-01 | El sistema acepta como entrada cualquier archivo de video local (cualquier resolución, fps — incluido fps variable de celular —, orientación y códec) sin requerir configuración manual de esos parámetros. | MUST | 1 |
| RF-02 | El sistema valida el archivo de entrada antes de procesar y falla con un mensaje claro (sin procesar el resto) si no es un video legible. | MUST | 1 |
| RF-03 | El sistema soporta perfiles de escenario configurables: `parqueadero`, `calle_lenta`, `calle_rapida` (>60 km/h) y `patrulla` (cámara en vehículo). El perfil seleccionado ajusta el comportamiento del pipeline. | MUST | 1 |
| RF-04 | El sistema procesa video de cámara fija o de cámara montada en un vehículo; el operador declara el modo (`estatico` o `movil`) al elegir el perfil (ADR-017, cambio 2026-10-03). | MUST | 1 |
| RF-05 | El sistema procesa video diurno y nocturno con iluminación urbana. No se contempla IR. | MUST | 1 |
| RF-06 | El sistema detecta vehículos y clasifica al menos los tipos `car`, `motorcycle`, `bus` y `truck`. | MUST | 1, 3 |
| RF-07 | El sistema detecta la placa dentro de cada vehículo detectado (carros: delantera y trasera; motos: solo trasera). | MUST | 1 |
| RF-08 | El sistema mantiene un track por vehículo a lo largo del video, tanto con cámara fija como con cámara en movimiento. | MUST | 1 |
| RF-09 | El sistema aplica OCR sobre el recorte de placa de cada lectura, devolviendo texto y una confianza numérica. | MUST | 1 |
| RF-10 | El sistema consolida las lecturas de cada track mediante votación, produciendo una lectura consolidada por track. | MUST | 1 |
| RF-11 | La consolidación aplica corrección posicional de caracteres confundibles: 0↔O, 1↔I, 8↔B, 5↔S. | MUST | 1 |
| RF-12 | El texto consolidado se valida contra el catálogo de formatos de placa (sección 6) usando las regex allí definidas. | MUST | 1 |
| RF-13 | Un texto que no coincide con ningún formato del catálogo se registra como formato no reconocido y queda para revisión (aplica a placas extranjeras). | MUST | 3 |
| RF-14 | El sistema verifica coherencia entre el formato detectado y el tipo de vehículo: p. ej. un formato de moto detectado en un `car` produce estado `unverified`. | MUST | 3 |
| RF-15 | Los formatos del catálogo marcados como no verificados (`verified = false`) **nunca** se confirman automáticamente: siempre van a revisión. | MUST | 3 |
| RF-16 | Cada avistamiento tiene uno de cuatro estados: `confirmed`, `unverified`, `rejected`, `corrected`. | MUST | 6, 7 |
| RF-17 | Por defecto la precisión manda: ante duda, la lectura queda `unverified`. Se acepta perder placas a cambio de no confirmar una lectura incorrecta. | MUST | 6 |
| RF-18 | Las lecturas de baja confianza se persisten como `unverified` junto con su recorte, para que sean revisables. | MUST | 7 |
| RF-19 | El catálogo de formatos es editable desde configuración (archivo de config, no código) e incluye por formato: categoría, colores, regex, filas, campo `verified` y fuente. | MUST | 3 |
| RF-20 | Solo se persiste el texto de la placa: no se clasifica ni se guarda el color de la placa. | MUST | 3 |
| RF-21 | Se persiste un registro de avistamiento por cada paso de un vehículo (por track). Si la misma placa pasa dos veces, se generan dos avistamientos. | MUST | 4 |
| RF-22 | Existe además una tabla de placas única global, sin duplicados de texto de placa. | MUST | 4 |
| RF-23 | Cada avistamiento guarda un timestamp relativo al inicio del video, en milisegundos. | MUST | 5 |
| RF-24 | Cada avistamiento guarda su nivel de confianza (o el insumo para calcularlo) y el tipo de vehículo. | MUST | 5, 6 |
| RF-25 | El recorte de placa de cada avistamiento se guarda cifrado en disco. | MUST | 10 |
| RF-26 | La base de datos está cifrada; la clave se almacena en el llavero del sistema operativo, nunca en el repo ni en texto plano. | MUST | 10 |
| RF-27 | Existe una CLI de revisión que muestra el recorte y permite al operador confirmar, corregir o descartar la lectura. | MUST | 7 |
| RF-28 | La CLI permite procesar un video, revisar, exportar a CSV y purgar. La interfaz gráfica es la web local de RF-36. | MUST | 11 |
| RF-36 | Existe una interfaz web local (ADR-016: `lector-web`, solo en 127.0.0.1, con token de arranque y cookie de sesión) que permite procesar un video con progreso y cancelación, listar y filtrar avistamientos con su recorte, revisarlos con teclado, ir al instante del video en que aparece la placa, exportar CSV, purgar y ver métricas. La GUI PySide6 (ADR-015) se retiró en la spec 073. | SHOULD | cambio 2026-09-27 (ADR-015); 2026-10-04 (ADR-016, spec 073) |
| RF-37 | Solo se leen, guardan y muestran placas cuyo ancho en el frame alcanza el mínimo de cercanía del perfil; las placas más lejanas se descartan antes de leerlas (ADR-017, docs/09). | MUST | cambio 2026-10-03 |
| RF-29 | La exportación a CSV está disponible desde la CLI. | MUST | 11 |
| RF-30 | La purga por retención se ejecuta automáticamente al iniciar cada ejecución y también está disponible como comando manual. Retención por defecto: recortes 30 días, registros 90 días. | MUST | 10 |
| RF-31 | Los logs enmascaran las placas: nunca se escribe una placa en claro en un log. | MUST | 10 |
| RF-32 | La descarga de modelos es un paso de setup explícito y separado del pipeline, con un manifiesto SHA-256 que se verifica antes de cargar cada modelo. Los modelos se cargan solo desde rutas locales. | MUST | 8, restricciones técnicas |
| RF-33 | El pipeline no realiza ninguna llamada de red durante el procesamiento. | MUST | restricciones técnicas |
| RF-34 | La arquitectura admite en el futuro una fuente de stream (celular como cámara enviando al PC) sin reescribir el pipeline. v1 procesa solo archivos locales en batch. | SHOULD | 2 |
| RF-35 | Un solo operador local usa el sistema; no hay autenticación multiusuario ni control de acceso por roles. | MUST | 10 |

## 5. Requisitos no funcionales

| ID | Categoría | Requisito | Método de medición |
|---|---|---|---|
| RNF-01 | Rendimiento | Procesar a 1× o más rápido (tiempo total ≤ duración del video) para videos ≤1080p a ≤30 fps. **(aprobada por el usuario 2026-09-24)** | Medir tiempo de pared del proceso completo contra duración del video, sobre un set fijo de videos de referencia, en la PC de referencia (RTX 5050). |
| RNF-02 | Rendimiento | Videos de resolución mayor se procesan igual, pero **no** se garantiza 1×. | Misma medición que RNF-01, reportada aparte y sin umbral de fallo. |
| RNF-03 | Rendimiento | El sistema puede ejecutarse en CPU, sin garantía de 1×. | Ejecutar el pipeline con CUDA deshabilitado y registrar que completa sin error (el tiempo se reporta, no se exige). |
| RNF-04 | Recursos | VRAM pico ≤ 4 GB como objetivo. **(aprobada por el usuario 2026-09-24)** Límite duro absoluto: 8 GB (todos los modelos simultáneos deben caber). | Muestrear el uso de VRAM (p. ej. `nvidia-smi` en bucle o el pico reportado por PyTorch) durante el procesamiento completo; el pico debe quedar bajo el objetivo y nunca alcanzar el límite duro. |
| RNF-05 | Portabilidad | Los modelos usados deben ser pequeños y exportables a formatos portables (ONNX) pensando en correr fuera de la PC del usuario. | Exportar cada modelo a ONNX y verificar que sus salidas coinciden con la versión original sobre un lote de prueba dentro de una tolerancia (PENDIENTE DE VALIDAR; se fija en Fase 3). |
| RNF-06 | Entorno | Debe funcionar sobre Fedora 44, driver NVIDIA 610.57, con un build de PyTorch con CUDA ≥ 12.8 que soporte sm_120 (cu130 para PyTorch 2.14.0). | Correr el pipeline completo en la PC de referencia y verificar que no hay errores de kernel/CUDA y que la GPU reporta capacidad de cómputo 12.0 (sm_120). |
| RNF-07 | Aislamiento de red | Cero llamadas de red en tiempo de ejecución del pipeline. La descarga de modelos ocurre solo en el paso de setup, desde rutas/hosts explícitos. | Ejecutar el pipeline con la red bloqueada (o capturando tráfico) y verificar 0 conexiones salientes. |
| RNF-08 | Integridad de modelos | Todo modelo se carga desde ruta local y se verifica contra su SHA-256 en el manifiesto antes de usarse; una discrepancia aborta la carga. | Ejecutar la carga con un modelo alterado y comprobar que falla; ejecutar con los modelos correctos y comprobar que carga. |
| RNF-09 | Seguridad | Base de datos y recortes cifrados en reposo. Clave custodiada en el llavero del SO, nunca en el repo ni en variables persistidas en claro. | Inspeccionar los archivos en disco y verificar que no son legibles sin la clave; verificar que la clave no aparece en el repo ni en la configuración versionada. |
| RNF-10 | Privacidad | 100 % de los recortes cifrados en disco. Ninguna placa en claro en logs. Ningún dato real (videos, recortes, placas, clave) se envía a la API externa del implementador. | Buscar patrones de placas en los logs y en los archivos de salida; auditar el tráfico hacia el servicio externo durante el flujo de trabajo. |
| RNF-11 | Privacidad | Retención por defecto: recortes 30 días, registros 90 días, con purga automática al iniciar cada ejecución y comando manual de purga. | Insertar datos con fecha antigua y verificar que la siguiente ejecución los purga; ejecutar la purga manual y verificar el mismo resultado. |
| RNF-12 | Privacidad | Permisos de archivos restrictivos: 0600 para archivos de datos y 0700 para directorios de datos. | `stat` sobre los archivos y directorios generados y comparar los bits de permiso. |
| RNF-13 | Mantenibilidad | Clean Architecture y SOLID; type hints obligatorios en todo el código; `mypy` en modo strict sin errores; tests con `pytest`. | Ejecutar `mypy --strict` y `pytest` en CI/local: 0 errores de tipos y suite en verde. |
| RNF-14 | Reproducibilidad | Versiones fijadas con lockfile y versión de Python fijada para el proyecto. | Recrear el entorno desde el lockfile en una máquina limpia y verificar que las versiones instaladas coinciden exactamente con las fijadas. |
| RNF-15 | Cumplimiento legal | Manejo de datos personales conforme a la Ley 1581 de 2012 (las placas son dato personal): cifrado, retención limitada, operador único local. | Revisión documental de los controles anteriores (RNF-09 a RNF-12) y registro de la base legal de tratamiento. |
| RNF-16 | Licenciamiento | El proyecto es público y acepta la licencia AGPL-3.0 de Ultralytics. | Revisar la declaración de licencias del repo y verificar el cumplimiento de AGPL-3.0 al publicarse. |

## 6. Catálogo de formatos de placa colombianos

Formato de regex: `L` = letra, `D` = dígito.

| Categoría | Colores | Regex | Filas | Verificado | Fuente |
|---|---|---|---|---|---|
| Particular | fondo amarillo, caracteres negros | `^[A-Z]{3}\d{3}$` | 1 + municipio | Sí | Res. 708/1991 art. 6; Ficha Técnica MT 001 |
| Público | fondo blanco, negros | `^[A-Z]{3}\d{3}$` | 1 + municipio | Sí | Res. 708/1991; Ficha MT 001 |
| Oficial | amarillo según Res. 708/1991 (Wikipedia dice blanco sobre verde: contradicción sin resolver) | `^[A-Z]{3}\d{3}$` | 1 + municipio | Parcial | Res. 708/1991 |
| Moto actual | amarillo, negros | `^[A-Z]{3}\d{2}[A-Z]$` | 1 fila + "COLOMBIA"; solo placa trasera | Sí | Res. 4923/1994 |
| Moto antigua | amarillo, negros | `^[A-Z]{3}\d{2}$` | 1 + "COLOMBIA" | Sí | Ficha MT 001 §4.2 |
| Motocarro | amarillo (particular) / blanco (público) | `^\d{3}[A-Z]{3}$` | 1 + "COLOMBIA" | Sí | Res. 1421/2011 |
| Diplomático (diseño 2015) | blanco con franja azul superior | `^[MDCAO][A-Z]{2}\d{3}$` (subconjunto de LLLDDD) | 1 | Sí (derogada por Res. 6705/2019; cambios **NO VERIFICADOS**) | Res. 1690/2015 |
| Moto diplomática | blanco con franja azul | `^MCD\d{3}$` | 1 | Sí | Res. 1690/2015 art. 3 |
| Diplomático antiguo | azul, caracteres blancos | `^(CD\|CC\|AT\|OI)\d{4}$` | 1 | Sí (citado en Res. 1690/2015) | Res. 3458/2000 |
| Antiguo / clásico | blanco con bandas azules | `^[A-Z]{3}\d{3}$` | palabra + 1 + municipio | Sí | Res. 3257/2018 |
| Remolque / semirremolque (placa VERDE) | verde, caracteres blancos | `^[RS]\d{5}$` | 1 + "COLOMBIA" | **No** (solo prensa) | Semana 2026 |
| Importación temporal | roja | `^T\d{4}$` | — | **No** (prensa/Wikipedia; ya no se expedirían) | — |
| Policía / Fuerzas Militares | — | NO VERIFICADO | — | **No** | — |
| Maquinaria | ya no usa placa: código de 8 caracteres pintado | NO VERIFICADO | — | — | Res. 20243040056195/2024 art. 13 |

Notas adicionales del catálogo:

- **Dimensiones verificadas**: placa de carro 330×160 mm; placa de moto y motocarro 235×105 mm
  (caracteres 54×28 mm).
- **Cantidad de placas por vehículo**: carros llevan placa delantera y trasera; motos solo trasera;
  remolques una.
- **Letras excluidas de las series** (Ñ, O, I, Q): NO VERIFICADO.
- **Formatos solapados**: el texto `LLLDDD` no distingue particular / público / oficial / antiguo /
  diplomático. Esto es aceptable porque solo se guarda el texto y la "familia de formato".

## 7. Fuera de alcance (v1)

| Excluido | Razón / nota |
|---|---|
| Streaming en vivo y app móvil (celular como cámara) | v1 procesa archivos locales en batch; la arquitectura no debe impedir agregarlo después (RF-34). |
| VLM y PaddleOCR como lectores de placa | El diseño debe permitir agregarlos como lectores alternativos, pero no se implementan en v1. |
| Clasificación de color o tipo de servicio de la placa | Solo se guarda el texto (RF-20). |
| Acceso remoto | La interacción es por CLI (RF-28) o por la web local (RF-36), que solo escucha en 127.0.0.1 (ADR-016, SEG-28); no hay acceso desde otro equipo. |
| Multiusuario y control de acceso por roles | Un solo operador local (RF-35). |
| Identificación de personas | Fuera del propósito del sistema. |
| Integración con RUNT u otras bases externas | Implica llamadas de red y tratamiento de datos de terceros. |
| Datasets RodoSol-ALPR y UFPR-ALPR | Descartados explícitamente por el usuario. |
| Placas extranjeras | No se reconocen: se guardan como formato no reconocido → revisión (RF-13). |

## 8. Criterios de éxito medibles

Todas las metas fueron aprobadas por el usuario el 2026-09-24.
El set de evaluación y su formato se definen en `docs/04-evaluacion.md` (Fase 5).

| # | Métrica | Meta | Cómo se mide |
|---|---|---|---|
| M-01 | Precisión de placas `confirmed` (texto exacto) | ≥ 98 % **(aprobada por el usuario 2026-09-24)** | Sobre el set de evaluación anotado: de todas las lecturas `confirmed`, fracción cuyo texto coincide exactamente con la verdad terreno. |
| M-02 | Recall de placas únicas considerando `confirmed` + `unverified` | ≥ 90 % **(aprobada por el usuario 2026-09-24)** | Placas únicas correctas detectadas (en cualquiera de los dos estados) / placas únicas presentes en el video. |
| M-03 | Recall de placas únicas solo `confirmed` | ≥ 75 % **(aprobada por el usuario 2026-09-24)** | Placas únicas confirmadas correctamente / placas únicas presentes en el video. |
| M-04 | CER del OCR sobre recortes de evaluación | ≤ 3 % tras fine-tuning **(aprobada por el usuario 2026-09-24)** | Distancia de edición a nivel de carácter entre el texto OCR y la verdad terreno, sumada sobre todos los recortes del set. |
| M-05 | Velocidad | ≥ 1× en RTX 5050 para ≤1080p30 (confirmado por el usuario como 1×) | Tiempo de pared del pipeline completo vs duración del video, en la PC de referencia. |
| M-06 | VRAM pico | ≤ 4 GB objetivo **(aprobada por el usuario 2026-09-24)**; 8 GB límite duro (confirmado) | Muestreo del uso de VRAM durante el procesamiento. |
| M-07 | Aislamiento de red | 0 llamadas de red durante el procesamiento (confirmado) | Captura de tráfico o ejecución con red bloqueada. |
| M-08 | Privacidad en logs | 0 placas en claro en logs (confirmado) | Búsqueda de patrones de placa sobre los archivos de log generados. |
| M-09 | Cifrado en disco | 100 % de recortes cifrados en disco (confirmado) | Verificación de que cada archivo de recorte es ilegible sin la clave. |

## 9. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Poco dato colombiano público: ≈1.800 imágenes de detección, 926 con cajas por carácter, pocas motos, ninguna con transcripción de texto (fuentes en C-11). | El fine-tuning del OCR y la detección de placas pueden quedar cortos; sobreajuste al formato de carro particular. | Complementar con videos propios (calle y parqueadero, día y noche) y placas sintéticas; priorizar datos con transcripción para el OCR; medir por subgrupo (moto vs carro). |
| El OCR preentrenado no incluye Colombia en su entrenamiento (fast-plate-ocr 1.1.0: en LatAm solo AR, BR, MX). | El modelo base leerá mal el formato y los caracteres colombianos hasta que se haga fine-tuning. | Fine-tuning con placas colombianas + validación de formato + corrección posicional + votación por track. |
| Desenfoque de movimiento a >60 km/h y en condiciones nocturnas. | Placas ilegibles o ilegibles parcialmente; caída de recall. | Perfil de escenario `calle_rapida` con parámetros propios; votación por track para recuperar caracteres en algunos frames; aceptar `unverified` en lugar de confirmar mal. |
| Cámara en movimiento (celular en mano o en vehículo) degrada el tracking. | Se fragmentan los tracks y se pierden avistamientos o se duplican. | Diseñar el tracking para cámara móvil (RF-08); perfiles de escenario; validar explícitamente con videos grabados en movimiento. |
| Formatos de placa no verificados (remolque verde, importación temporal roja, policía/fuerzas militares, maquinaria, y la contradicción de color del formato oficial). | Confirmar un formato inexistente o mal definido produce datos falsos. | Campo `verified` en el catálogo: los formatos no verificados nunca se confirman automáticamente (RF-15); quedan en revisión manual. |
| Licencia AGPL-3.0 de Ultralytics. | Obligaciones de copyleft sobre el código derivado. | Aceptado porque el repo será público (C-05); dejar la licencia explícita en el repo. |
| Manejo de datos personales (Ley 1581 de 2012): las placas son dato personal. | Sanción legal y daño a terceros si se filtran los datos. | Cifrado de BD y recortes, clave en llavero del SO, permisos 0600/0700, retención con purga automática, enmascarado en logs, y ningún dato real hacia la API externa. |

## 10. Pendientes y no verificados

| # | Ítem | Tipo |
|---|---|---|
| P-01 | Duplicados entre datasets de Roboflow y veracidad de las licencias declaradas por quien los subió (ver C-11). | NO VERIFICADO (se revisa en Fase 5) |
| P-02 | Color oficial del formato **Oficial**: Res. 708/1991 dice amarillo; Wikipedia dice blanco sobre verde. Contradicción sin resolver. | NO VERIFICADO |
| P-03 | Cambios introducidos por Res. 6705/2019 al formato diplomático 2015 (lo deroga; no se verificó qué lo reemplaza). | NO VERIFICADO |
| P-04 | Formato de placas de **Policía / Fuerzas Militares**. | NO VERIFICADO |
| P-05 | Formato de **maquinaria**: la resolución indica un código de 8 caracteres pintado; el detalle del código no está verificado. | NO VERIFICADO |
| P-06 | Letras excluidas de las series (Ñ, O, I, Q). | NO VERIFICADO |
| P-07 | Formato de **remolque/semirremolque** (placa verde, `^[RS]\d{5}$`): verificado solo por prensa, no por fuente oficial. | NO VERIFICADO (fuente: prensa) |
| P-08 | Formato de **importación temporal** (roja, `^T\d{4}$`): fuente prensa/Wikipedia; además se indica que ya no se expedirían. | NO VERIFICADO |
| P-09 | Metas numéricas de la sección 8. | Aprobadas por el usuario (2026-09-24) |
| P-10 | Objetivo de VRAM pico ≤ 4 GB (RNF-04). | Aprobado por el usuario (2026-09-24) |
| P-11 | Formato y composición del set de evaluación. | Se define en `docs/04-evaluacion.md` (Fase 5) |

## 11. Glosario

| Término | Definición |
|---|---|
| **track** | Secuencia de detecciones del mismo vehículo a lo largo de los frames, mantenida por el componente de tracking. Un vehículo que pasa una vez produce un track. |
| **avistamiento** (sighting) | Registro persistido de un paso de un vehículo por el video, asociado a un track, con timestamp relativo, confianza, tipo de vehículo y recorte cifrado. |
| **lectura** (reading) | Texto de placa obtenido por OCR a partir de un recorte, en un frame concreto. Varias lecturas pertenecen a un mismo track. |
| **consolidación** | Proceso que combina las lecturas de un track (votación + corrección posicional + validación de formato) para producir una única lectura consolidada. |
| **familia de formato** | Conjunto de formatos que comparten el mismo patrón de texto; p. ej. `LLLDDD` agrupa particular, público, oficial, antiguo y diplomático, que no se distinguen solo por el texto. |
| **confirmed** | Estado de una lectura consolidada que superó la validación con un formato verificado y la coherencia con el tipo de vehículo. Debe ser correcta casi siempre. |
| **unverified** | Estado de una lectura dudosa (baja confianza, formato no verificado, incoherencia con el tipo de vehículo o formato no reconocido). Requiere revisión manual. |
| **rejected** | Estado de un avistamiento descartado por el operador en la CLI de revisión. |
| **corrected** | Estado de un avistamiento cuyo texto fue corregido manualmente por el operador en la CLI de revisión. |
| **perfil de escenario** | Configuración predefinida que ajusta el pipeline según el tipo de escena: `parqueadero`, `calle_lenta`, `calle_rapida` (>60 km/h). |
| **recorte** | Imagen de la región de la placa extraída de un frame, cifrada en disco y asociada a un avistamiento. |
