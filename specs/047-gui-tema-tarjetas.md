# 047 - GUI: tema visual, tarjeta de placa y cuadrícula de tarjetas

## Objetivo
Primera pieza del rediseño de la GUI (decisión del usuario 2026-09-27: "quiero ver los recortes de cada matrícula con su
lectura; una buena UI no debería necesitar explicación"). Esta spec crea los componentes visuales reutilizables: un
tema claro y consistente, una **tarjeta de placa** (recorte + lectura grande con aspecto de placa + estado en color) y
una **cuadrícula de tarjetas** con selección y navegación por teclado. Las specs 048 y 049 los usan; esta spec no cambia
todavía la ventana principal.

## Depende de
042, 044.

## Archivos rectores aplicables
- ADR-015; ARQUITECTURA.md §6 (funciones ≤ 20 sentencias, clases ≤ 150 líneas, módulos ≤ 300), §7.
- reglas-seguridad.md SEG-07 (recortes solo en memoria), SEG-27 (sin portapapeles, sin estado persistido, títulos
  constantes).

## Archivos a crear/modificar
- `src/lector_placas/gui/theme.py` (nuevo: colores, hoja de estilo, `apply_theme`)
- `src/lector_placas/gui/labels.py` (añadir textos de estado para el operador, motivos en lenguaje llano, `format_plate`
  y `short_time`)
- `src/lector_placas/gui/images.py` (añadir `bgr_to_pixmap`)
- `src/lector_placas/gui/plate_card.py` (nuevo: `PlateCard`)
- `src/lector_placas/gui/card_grid.py` (nuevo: `CardGrid`, `EmptyState`, `columns_for_width`)
- `src/lector_placas/gui/app.py` (llama `apply_theme(app)` justo después de crear la `QApplication`)
- `tests/unit/gui/test_theme.py`, `tests/unit/gui/test_plate_card.py`, `tests/unit/gui/test_card_grid.py` (nuevos)
- `tests/unit/gui/test_labels.py`, `tests/unit/gui/test_images.py` (añadir casos)

## Dependencias externas
Ninguna nueva.

## Interfaces y tipos involucrados
Contrato (firmas, sin implementación):

```python
# gui/theme.py
ACCENT: Final[str] = "#2563EB"
BACKGROUND: Final[str] = "#F5F6F8"
SURFACE: Final[str] = "#FFFFFF"
BORDER: Final[str] = "#E1E4E8"
TEXT: Final[str] = "#1F2328"
MUTED: Final[str] = "#656D76"
PLATE_YELLOW: Final[str] = "#FFD500"
STATUS_COLORS: Final[Mapping[ReviewStatus, tuple[str, str]]]   # (texto, fondo) de la etiqueta de estado
STYLESHEET: Final[str]
def apply_theme(app: QApplication) -> None: ...

# gui/labels.py (añadidos)
STATUS_BADGES: Final[Mapping[ReviewStatus, str]]     # unverified "Por revisar", confirmed "Confirmada",
                                                     # corrected "Corregida", rejected "Descartada"
REASON_TEXTS: Final[Mapping[UnverifiedReason, str]]
def format_plate(text: str) -> str: ...
def short_time(ms: int) -> str: ...

# gui/images.py (añadido)
def bgr_to_pixmap(image: ImageBGR, max_width: int, max_height: int) -> QPixmap: ...

# gui/plate_card.py
CARD_WIDTH: Final[int] = 260
CARD_HEIGHT: Final[int] = 176
CROP_BOX: Final[tuple[int, int]] = (244, 84)
NO_IMAGE_TEXT: Final[str] = "sin imagen"
class PlateCard(QFrame):
    clicked = Signal(int)                                  # sighting_id
    def __init__(self, record: SightingRecord, crop: QPixmap | None, parent: QWidget | None = None) -> None: ...
    def sighting_id(self) -> int: ...
    def update_record(self, record: SightingRecord) -> None: ...
    def set_selected(self, selected: bool) -> None: ...
    def is_selected(self) -> bool: ...

# gui/card_grid.py
GRID_SPACING: Final[int] = 12
def columns_for_width(width: int) -> int: ...
class EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def set_message(self, title: str, hint: str) -> None: ...
class CardGrid(QScrollArea):
    selection_changed = Signal(int)                        # sighting_id seleccionado
    def __init__(self, parent: QWidget | None = None) -> None: ...
    def set_records(self, records: Sequence[SightingRecord], crops: Mapping[int, QPixmap | None]) -> None: ...
    def append_records(self, records: Sequence[SightingRecord], crops: Mapping[int, QPixmap | None]) -> None: ...
    def update_record(self, record: SightingRecord) -> None: ...
    def remove(self, sighting_id: int) -> None: ...
    def ids(self) -> list[int]: ...
    def select(self, sighting_id: int | None) -> None: ...
    def selected_id(self) -> int | None: ...
    def next_id(self, sighting_id: int) -> int | None: ...
    def set_empty_message(self, title: str, hint: str) -> None: ...
```

## Comportamiento esperado
1. **`theme.py`**:
   - `STATUS_COLORS`: unverified `("#92400E", "#FEF3C7")` (ámbar), confirmed `("#166534", "#DCFCE7")` (verde),
     corrected `("#1E40AF", "#DBEAFE")` (azul), rejected `("#991B1B", "#FEE2E2")` (rojo).
   - `STYLESHEET` (Qt Style Sheet, una constante de texto construida con los colores anteriores) define: fondo
     `BACKGROUND` de `QMainWindow` y `QDialog`; `QPushButton` con esquinas de 6 px, relleno 6×14 px, borde `BORDER` y
     fondo `SURFACE`; `QPushButton[role="primary"]` con fondo `ACCENT` y texto blanco (y un tono más oscuro en
     `:hover`, más claro/gris en `:disabled`); `QPushButton[role="ghost"]` sin borde ni fondo; `QLineEdit`, `QComboBox` y
     `QSpinBox` con borde `BORDER` y esquinas de 6 px; `QProgressBar` con barra `ACCENT`; `QLabel[role="title"]` 20 px
     negrita; `QLabel[role="muted"]` en color `MUTED`; `QFrame#PlateCard` con fondo `SURFACE`, borde 1 px `BORDER`,
     esquinas de 10 px, y `QFrame#PlateCard[selected="true"]` con borde 2 px `ACCENT`; `QLabel#PlateText` con fondo
     `PLATE_YELLOW`, texto negro, borde 2 px `#1F2328`, esquinas de 4 px, fuente monoespaciada en negrita de 22 px y
     relleno 2×10 px.
   - `apply_theme(app)`: `app.setStyle("Fusion")` y `app.setStyleSheet(STYLESHEET)`. No lee ni escribe archivos.
2. **`labels.py`** (añadidos; lo existente no cambia):
   - `STATUS_BADGES` con los textos del contrato (son los que ve el operador; `STATUS_LABELS` sigue igual).
   - `REASON_TEXTS`: insufficient_readings "Se leyó pocas veces"; low_confidence "El lector no estaba seguro";
     low_agreement "Las lecturas no coinciden entre sí"; unrecognized_format "No parece una placa colombiana";
     unverified_format "Formato de placa poco común"; vehicle_format_mismatch "El formato no corresponde al tipo de
     vehículo"; ambiguous_format "Encaja en más de un formato".
   - `format_plate(text)`: si tiene 6 caracteres, `"ABC 123"` (espacio tras el tercero); en otro caso sin cambios.
   - `short_time(ms)`: `"m:ss"` (`83_456` → `"1:23"`, `0` → `"0:00"`); con una hora o más `"h:mm:ss"`
     (`3_723_004` → `"1:02:03"`).
3. **`bgr_to_pixmap(image, max_width, max_height)`**: `QPixmap.fromImage(bgr_to_qimage(image))` escalado para caber en
   la caja conservando la proporción (`KeepAspectRatio`, `SmoothTransformation`); nunca amplía por encima de 3× el
   tamaño original (para no pixelar recortes diminutos). Mismas validaciones que `bgr_to_qimage`.
4. **`PlateCard`** (`QFrame`, `objectName` `"PlateCard"`, tamaño fijo `CARD_WIDTH`×`CARD_HEIGHT`, cursor de mano):
   - De arriba a abajo: área del recorte de tamaño fijo `CROP_BOX`, centrada (el `QPixmap` recibido, o el texto
     `NO_IMAGE_TEXT` con `role="muted"` si es `None`); fila con la lectura (`QLabel` `objectName` `"PlateText"`,
     texto `format_plate(record.plate_text)`) y a la derecha la etiqueta de estado (`QLabel` con texto
     `STATUS_BADGES[status]`, colores de `STATUS_COLORS` aplicados con `setStyleSheet` en ese label, esquinas de 9 px,
     relleno 2×8 px); línea `role="muted"` con `f"{VEHICLE_LABELS[tipo].capitalize()} · {short_time(first_seen_ms)} ·
     {num_readings} lecturas"`.
   - La tarjeta no tiene título ni tooltip con la placa.
   - Clic izquierdo → emite `clicked(sighting_id)`. `set_selected(b)` fija la propiedad dinámica `selected` a
     `"true"`/`"false"` y repinta (`style().unpolish(self)`/`polish(self)`).
   - `update_record(record)`: exige el mismo `sighting_id` (si no, `InvalidEntityError`) y actualiza lectura, etiqueta y
     línea de datos; el recorte no cambia.
5. **`columns_for_width(width)`**: `max(1, (width + GRID_SPACING) // (CARD_WIDTH + GRID_SPACING))`.
6. **`EmptyState`**: dos `QLabel` centrados (título con `role="title"`, pista con `role="muted"` y ajuste de línea).
7. **`CardGrid`** (`QScrollArea` redimensionable, sin barra horizontal):
   - Contenedor interno con `QGridLayout` (espaciado `GRID_SPACING`, alineado arriba a la izquierda). Las tarjetas se
     colocan en orden de llegada, fila a fila, con `columns_for_width(viewport().width())` columnas; al cambiar el
     ancho (`resizeEvent`) se recolocan si cambia el número de columnas.
   - Sin tarjetas se muestra el `EmptyState` en lugar de la cuadrícula (mensaje por defecto: título "Nada por aquí",
     pista vacía; `set_empty_message` lo cambia).
   - `set_records` borra las tarjetas anteriores (`deleteLater`) y crea una por registro con el recorte de `crops`
     (`None` o ausente → sin imagen). `append_records` añade al final sin borrar. Ambos conservan la selección si la
     tarjeta seleccionada sigue existiendo; si no, no queda ninguna seleccionada.
   - `select(id)`: marca esa tarjeta, desmarca la anterior, la hace visible (`ensureWidgetVisible`) y emite
     `selection_changed(id)` solo si la selección cambió. `select(None)` o un id inexistente dejan sin selección y no
     emiten. El clic en una tarjeta llama `select`.
   - Teclado (con el foco en la cuadrícula; `setFocusPolicy(Qt.StrongFocus)`): Derecha/Izquierda → siguiente/anterior
     en el orden; Abajo/Arriba → misma columna en la fila siguiente/anterior (si no existe, la última/primera tarjeta);
     sin selección, cualquier flecha selecciona la primera. Las demás teclas pasan a la implementación base.
   - `update_record` actualiza la tarjeta de ese id (si no existe, no hace nada). `remove(id)` la quita y recoloca; si
     era la seleccionada, queda sin selección (no emite). `ids()` devuelve el orden visible. `next_id(id)` devuelve el
     id siguiente en el orden, o el anterior si era el último, o `None` si era el único o no existe.

## Casos borde y manejo de errores
- Placas de 5 o 7 caracteres: `format_plate` las deja igual.
- Recortes muy pequeños (p. ej. 30×10): se amplían como máximo 3×.
- Ningún texto de placa en títulos, tooltips, logs ni portapapeles.

## Tests de aceptación
Sin pantalla (conftest de la spec 042: `QT_QPA_PLATFORM=offscreen`, fixture `qapp`). Registros sintéticos
(`SightingRecord` construidos en el test con placas inventadas `ABC123`, `XYZ98K`, `ABC12D`) y recortes numpy.

1. `test_theme.py`:
   - `test_status_colors_cover_all_statuses`.
   - `test_stylesheet_uses_palette`: `STYLESHEET` contiene `ACCENT`, `PLATE_YELLOW`, `"#PlateCard"` y `"PlateText"`.
   - `test_apply_theme_sets_stylesheet_and_fusion`: tras `apply_theme(qapp)`, `qapp.styleSheet() == STYLESHEET` y el
     nombre del estilo es `fusion` (sin distinguir mayúsculas).
2. `test_labels.py` (añadir): `test_status_badges_and_reason_texts_cover_all_values`; `test_format_plate`
   (`"ABC123"` → `"ABC 123"`, `"ABC12D"` → `"ABC 12D"`, `"AB123"` y `"ABCD1234"` sin cambios); `test_short_time`
   (`0` → `"0:00"`, `83_456` → `"1:23"`, `3_723_004` → `"1:02:03"`).
3. `test_images.py` (añadir): `test_bgr_to_pixmap_fits_box_keeping_ratio` (200×50 en caja 100×100 → 100×25);
   `test_bgr_to_pixmap_caps_upscale` (30×10 en caja 244×84 → como máximo 90×30).
4. `test_plate_card.py`:
   - `test_card_shows_formatted_plate_badge_and_meta`: lectura `"ABC 123"`, etiqueta `"Por revisar"`, línea
     `"Carro · 0:05 · 4 lecturas"` para `first_seen_ms=5000`, `num_readings=4`.
   - `test_card_without_crop_shows_placeholder`.
   - `test_click_emits_sighting_id` (con `QTest.mouseClick`).
   - `test_selected_property_toggles`.
   - `test_update_record_changes_plate_and_badge` y `test_update_record_rejects_other_id`.
5. `test_card_grid.py`:
   - `test_columns_for_width`: `0` → 1, `272` → 1, `544` → 2, `900` → 3.
   - `test_empty_grid_shows_empty_state` y que `set_empty_message` cambia los textos.
   - `test_set_records_keeps_order_and_append_adds`.
   - `test_select_emits_once_and_marks_card`: seleccionar dos veces el mismo id emite una sola vez.
   - `test_keyboard_navigation`: con 5 tarjetas y 3 columnas forzadas (el test fija el ancho del viewport o sustituye
     el cálculo de columnas), Derecha, Abajo e Izquierda mueven la selección a los ids esperados; sin selección, una
     flecha selecciona la primera.
   - `test_remove_and_next_id`: `next_id` del último devuelve el anterior; tras `remove` de la seleccionada no hay
     selección.
   - `test_update_record_updates_card`.

## Definition of Done
- `uv run pytest tests/unit tests/architecture` pasa.
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- `wc -l src/lector_placas/gui/*.py`: ningún módulo pasa de 300 líneas; ninguna clase de 150.
