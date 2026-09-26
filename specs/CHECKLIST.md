# Checklist — cierre del diseño

- [x] 1. Verificar en el código de fast-plate-ocr 1.1.0: dónde guarda el entrenamiento el mejor modelo, opciones y nombre de salida de `export`, entry point de la CLI
- [x] 2. Escribir `specs/032-entrenamiento-ocr.md`
- [x] 3. Añadir el modelo OCR fine-tuneado al manifiesto (`docs/03-modelo-datos.md` §5)
- [x] 4. Verificar insumos del generador sintético (dimensiones verificadas, fuente tipográfica con licencia libre, versión de Pillow)
- [x] 5. Escribir `specs/033-generador-sintetico.md`
- [x] 6. Actualizar `specs/README.md` (estados 032–033)
- [x] 7. Revisión de consistencia cruzada (ARQUITECTURA, CONTEXT, reglas-seguridad, contratos ↔ specs)
- [x] 8. Actualizar memoria del proyecto

Pendiente del usuario (no bloquea): política para exportar recortes propios a entrenamiento (SEG-07 / SEG-03).
