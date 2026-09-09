# Garmin — MVP de descarga del histórico

## Alcance

Herramienta personal en Python, con `uv` para paquetes y ejecución. Corre localmente, sin interfaz propia e independiente del agente (Codex, Claude, OpenCode u otros).

Objetivo: descargar y conservar los FIT originales de todas las actividades de Garmin Connect. Simple, sin infraestructura innecesaria.

## M1 — Conectar con Garmin

- [ ] Inicializar el proyecto con `uv`.
- [ ] Implementar login y persistencia local de sesión fuera del repositorio.
- [ ] Listar actividades para comprobar el acceso.

Terminado cuando sea posible autenticarse y ver las actividades.

## M2 — Descargar el histórico

- [ ] Implementar `garmin sync --since YYYY-MM-DD --until YYYY-MM-DD`, con `--until` opcional.
- [ ] Descargar todos los deportes y guardar los FIT originales por año/mes, sin modificarlos.
- [ ] Registrar en SQLite lo mínimo: ID de Garmin, fecha, deporte, nombre y ruta del archivo.
- [ ] Evitar duplicados y permitir retomar descargas interrumpidas.

Las fechas son configurables e inclusivas. Sin `--until`, se descarga hasta el presente. Se puede ampliar el histórico ejecutando nuevamente con una fecha anterior.

Primera ejecución prevista:

```bash
uv run garmin sync --since 2026-04-15
```

La fecha no queda fijada en el código ni como restricción para otros usuarios.

Terminado cuando el histórico esté descargado y repetir el comando no duplique archivos.

## M3 — Verificar y dejarlo usable

- [ ] Comprobar con la cuenta real las descargas y la reanudación; informar actividades fallidas o sin FIT disponible.
- [ ] Mostrar un resumen de actividades descargadas, existentes y fallidas.
- [ ] Documentar instalación, login y sincronización con `uv run`.

Terminado cuando se pueda usar mediante los comandos documentados, sin pasos manuales adicionales.

## Fuera de este MVP

- Reconciliación de cambios posteriores en Garmin Connect.
- Parser y métricas de natación: se definirán con archivos reales.
- MCP, análisis mediante agentes, creación/programación de rutinas y gráficos.
- Validación de workouts en el reloj y evaluación del repositorio de referencia para crearlos.

## Contexto para las siguientes etapas

- Usuario inicial: Forerunner 570 de 47 mm, piscina de 25 m y uso habitual de rutinas en el reloj.
- Modelo de reloj y longitud de piscina deberán ser configurables cuando sean necesarios, sin valores fijos en el código.
- El agente deberá presentar la rutina y consensuarla con el usuario antes de crearla y programarla en Garmin.
- El objetivo más amplio se conserva en `garmin-swim-agent-plan.md`; este documento delimita la primera entrega.
