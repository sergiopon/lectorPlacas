# 072 - Publicación de la web: capturas del modo demo y chequeo de nivel F de la web

## Objetivo
Preparar la web para el README de portafolio:
1. **Capturas** de las pantallas principales, generadas con Playwright sobre `lector-web --demo` (solo datos
   sintéticos, SEG-10), en `docs/img/`.
2. **Nivel F**: un chequeo nuevo en `scripts/nivel_f.py` que arranca la web y comprueba que solo escucha en
   `127.0.0.1`, que rechaza un `Host` ajeno y que `/api/*` exige sesión (SEG-28).

El texto del README lo escribe el orquestador al integrar (no es parte de esta spec).

## Depende de
068, 069, 071.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-10, SEG-28; docs/06-plan-pruebas.md §3 (nivel F).

## Archivos a crear/modificar
- `frontend/e2e/capturas.spec.ts` (nuevo)
- `scripts/nivel_f.py`
- `tests/integration/test_nivel_f_web.py` (nuevo)
- `docs/img/` (las cuatro capturas; las genera el comando del Definition of Done, no se dibujan a mano)

## Dependencias externas
Ninguna nueva. `ss` (iproute2) para listar sockets en escucha: presente en este equipo (`/usr/bin/ss`).

## Comportamiento esperado

### 1. `frontend/e2e/capturas.spec.ts`
- `test.skip(!process.env.LECTOR_CAPTURAS, "solo con LECTOR_CAPTURAS=1")` al principio del archivo; así `npm run e2e`
  normal no las genera.
- `test.use({ viewport: { width: 1440, height: 900 }, colorScheme: "light" })`.
- Una sola prueba `capturas del modo demo` que, en este orden y sin modificar datos: abre `/`, pulsa "Lecturas",
  espera a que haya al menos una tarjeta, pulsa la primera y guarda `page.screenshot({ path: "../docs/img/web-lecturas.png" })`;
  pulsa "Procesar" en la navegación principal (`page.getByRole("navigation").getByRole("button", { name: "Procesar" })`), elige `demo_entrada.mp4` y guarda `../docs/img/web-procesar.png` (sin pulsar "Procesar");
  pulsa "Métricas", espera a las cuatro tarjetas y guarda `../docs/img/web-metricas.png`; pulsa "Historial" y guarda
  `../docs/img/web-historial.png`.
- El nombre del archivo (`capturas`) ordena antes que `demo.spec.ts`, así que con `workers: 1` las capturas se toman
  antes de que la otra prueba cambie datos.

### 2. `scripts/nivel_f.py`
Nueva función `check_web_loopback() -> tuple[bool, str]` y se añade a `collect_checks` como
`("7. web solo en loopback", *check_web_loopback())`, **antes** de la velocidad (los nombres "5. velocidad" y "6. VRAM"
no cambian). También se actualiza el docstring del módulo con la línea
`7. web             → escucha solo en 127.0.0.1; Host ajeno → 400; /api sin sesión → 401`.
1. Si `shutil.which("ss")` es `None` → `(False, "ss no disponible; omitido")`.
2. Lanza `subprocess.Popen([sys.executable, "-c", "from lector_placas.web.app import main; raise SystemExit(main())", "--demo", "--no-browser", "--port", "0"], cwd=ROOT, stdout=PIPE, stderr=PIPE, text=True)`.
3. Lee `stdout` línea a línea (máximo 30 s) hasta una que cumpla `^lectorPlacas web en http://127\.0\.0\.1:(\d+)/$`;
   si no aparece → termina el proceso y `(False, "lector-web no arrancó")`.
3b. Espera a que el puerto acepte conexiones: reintenta `socket.create_connection(("127.0.0.1", puerto), timeout=1)`
   cada 0,2 s durante un máximo de 15 s (cerrando cada socket); si nunca acepta → termina el proceso y
   `(False, "lector-web no acepta conexiones")`. (`lector-web` imprime la URL antes de que Uvicorn empiece a escuchar.)
4. `ss -Hltn` (texto): `ok_bind` es verdadero si alguna línea contiene `127.0.0.1:<puerto>` y ninguna contiene
   `0.0.0.0:<puerto>`, `*:<puerto>` ni `[::]:<puerto>`.
5. Con `http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)`: `GET /` con cabecera `Host: ejemplo.invalid:<puerto>`
   → `ok_host` si el estado es 400; `GET /api/health` con `Host: 127.0.0.1:<puerto>` y sin cookie → `ok_auth` si es 401.
6. En un `finally`: `proceso.send_signal(signal.SIGINT)`, `wait(timeout=10)` y, si vence, `kill()`.
7. Devuelve `(ok_bind and ok_host and ok_auth, f"bind={'ok' if ok_bind else 'MAL'} host={'ok' if ok_host else 'MAL'} auth={'ok' if ok_auth else 'MAL'} puerto={puerto}")`.

### 3. `tests/integration/test_nivel_f_web.py`
- `test_web_loopback_check_passes`: importa `scripts/nivel_f.py` con `importlib.util.spec_from_file_location` y comprueba
  que `check_web_loopback()` devuelve `ok` verdadero y que el detalle empieza por `bind=ok host=ok auth=ok`. Se omite
  con `pytest.skip("ss no disponible")` si `shutil.which("ss")` es `None`.

## Casos borde y manejo de errores
- El chequeo usa el modo demo: no necesita clave en el keyring ni modelos, y no toca `data/`.
- Las capturas solo contienen datos sintéticos del modo demo.

## Fuera de alcance
- El texto del README, `docs/06` y la portada del repositorio (los escribe el orquestador).

## Definition of Done
- [ ] `uv run pytest -q` (suite completa), `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy src`
      limpios.
- [ ] En `frontend/`: `npm run typecheck` y `npm run e2e` en verde (las capturas se omiten).
- [ ] En `frontend/`: `LECTOR_CAPTURAS=1 npx playwright test e2e/capturas.spec.ts` genera los cuatro PNG en `docs/img/`
      (listar sus tamaños).
