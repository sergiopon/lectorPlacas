#!/usr/bin/env bash
# Graba el recorrido de la interfaz con Playwright y lo convierte en el GIF del README.
set -euo pipefail

cd frontend && npm run build && LECTOR_MEDIOS=1 npx playwright test e2e/medios.spec.ts && cd ..

ffmpeg -y -i docs/img/demo.webm -vf "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=5" docs/img/demo.gif

rm docs/img/demo.webm
ls -l docs/img/demo.gif
