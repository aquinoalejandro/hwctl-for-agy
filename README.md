# hwctl - Hardware Diagnostic & Control Layer for Antigravity

**hwctl** es la capa de herramientas, telemetría y control de hardware para Windows diseñada específicamente para ser operada por el agente de IA **Antigravity**.

> [!IMPORTANT]
> **Separación de Responsabilidades**:
> Este software **NO contiene un agente de IA ni toma decisiones autónomas de diagnóstico**. No contiene reglas subjetivas (como `if temp > 90: fan_up()`). Su única función es actuar como los **ojos y manos** de Antigravity en el equipo: **observar → ejecutar de forma segura → devolver resultados estructurados en JSON**.

---

## 1. Arquitectura General

```text
                  ┌──────────────────────────────────────────────┐
                  │            Antigravity (AI Brain)            │
                  │   (Analiza, razona, decide experimentos)     │
                  └──────────────────────┬───────────────────────┘
                                         │ Comandos CLI / JSON
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HardwareController (API)                          │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│    Safety Guard      │   Rollback Manager   │       Audit Logger (JSONL)    │
│ (Límites 0-100%,     │ (Captura estado prev,│   (Registra timestamps,       │
│  timeouts, clamps)   │  restaura al salir)  │   parámetros, antes/después)  │
└──────────────────────┴──────────┬───────────┴───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Provider Registry                              │
├─────────────────────┬───────────────────┬───────────────────┬───────────────┤
│    AMD Providers    │  NVIDIA Provider  │  Intel Provider   │ Mock Provider │
│ • Windows: ADL SDK  │  (NVAPI / Stub)   │  (ControlLib Stub)│ (Simulación   │
│ • Linux/Arch: sysfs │                   │                   │  RX 580)      │
└─────────────────────┴───────────────────┴───────────────────┴───────────────┘
                                  │
                                  ▼
             Hardware Físico (Windows Drivers / Linux Kernel amdgpu)
```

---

## 2. Catálogo de Comandos CLI (Salida 100% JSON)

Todos los comandos emiten exclusivamente JSON a `stdout`, permitiendo que Antigravity lo parsee directamente.

### Consultas y Diagnóstico de Entorno

| Comando | Descripción |
| :--- | :--- |
| `python -m hwctl.cli describe-tools` | Devuelve el catálogo completo de herramientas y parámetros para la IA. |
| `python -m hwctl.cli check-environment` | Detecta si es Windows o Arch Linux/Linux, verifica permisos root/Admin, DLLs, OpenCL y conflictos. |
| `python -m hwctl.cli get-kernel-logs` | *(Linux/Arch)* Extrae los logs de `dmesg` del kernel para el driver `amdgpu` (alertas de SMC, firmware y hardware). |
| `python -m hwctl.cli get-system-info` | Devuelve OS (incluyendo distro Linux), CPU, RAM, Motherboard y procesos en ejecución. |
| `python -m hwctl.cli get-gpu-info` | Identificación de GPU, fabricante, VRAM, versión de driver y VBIOS. |
| `python -m hwctl.cli get-gpu-sensors` | Telemetría en tiempo real: temperaturas (núcleo y hotspot), RPM, clocks, power. |
| `python -m hwctl.cli get-gpu-fan-status` | Porcentaje de ventilador, RPM actual, límites min/max y modo de control. |
| `python -m hwctl.cli get-gpu-driver-info` | Estado de carga del driver ADL y adaptadores detectados. |
| `python -m hwctl.cli get-gpu-vbios-info` | Versión y número de parte de la VBIOS reportada por el driver. |

### Carga de GPU y Pruebas Térmicas Autónomas (Sin FurMark ni juegos)

| Comando | Parámetros | Descripción |
| :--- | :--- | :--- |
| `start-gpu-stress` | `[--duration 30]` | Inicia carga continua de shaders/cómputo GPU en background con auto-timeout. |
| `stop-gpu-stress` | - | Detiene la carga de GPU de inmediato. |
| `run-thermal-stress-test` | `[--duration 20] [--interval 1] [--emergency-temp 90]` | Ejecuta prueba de estrés bajo carga, recolecta serie temporal de temperatura/RPM y cuenta con corte de emergencia térmico. |

### Acciones (Mutación Segura)

| Comando | Parámetros | Descripción |
| :--- | :--- | :--- |
| `set-gpu-fan-percent` | `--percent <0-100>` | Fija la velocidad del ventilador. Captura snapshot previo para rollback. |
| `enable-gpu-manual-fan-control` | - | Desbloquea el controlador de ventiladores en modo manual. |
| `disable-gpu-manual-fan-control`| - | Vuelve al modo automático del controlador. |
| `reset-gpu-fan-control` | - | Failsafe para restablecer inmediatamente la curva automática del driver. |

### Pruebas Controladas y Diagnóstico

| Comando | Parámetros | Descripción |
| :--- | :--- | :--- |
| `run-fan-test` | `--steps 25,50,75,100 --hold 5 --interval 1` | Ejecuta una secuencia de escalones de ventilador, toma muestras y restaura el estado. |
| `create-diagnostic-snapshot` | - | Captura un snapshot atómico sincronizado (Sistema + GPU + Sensores + Procesos). |
| `create-diagnostic-report` | `[--output <ruta>]` | Guarda el snapshot en un archivo JSON en disco. |

---

## 3. Ejemplos de Salida Estructurada

### Acción Exitosa: `set-gpu-fan-percent --percent 75`
```json
{
  "success": true,
  "action": "set_gpu_fan_percent",
  "timestamp": "2026-10-08T21:43:49.472387+00:00",
  "requested_percent": 75.0,
  "reported_percent": 75.0,
  "reported_rpm": 2550,
  "temperature_c": 52.0,
  "power_w": 42.0
}
```

### Reporte de Error Estructurado: Violación de Seguridad
```json
{
  "success": false,
  "action": "set_gpu_fan_percent",
  "error": {
    "code": "SAFETY_VIOLATION",
    "message": "Requested fan speed 150.0% is out of safe range [0.0, 100.0]."
  },
  "timestamp": "2026-10-08T21:43:54.568774+00:00"
}
```

---

## 4. Auditoría y Logs (`logs/audit_hwctl.jsonl`)

Cada llamada a herramienta, cambio de estado, resultado o intervención de seguridad se registra en formato **JSON Lines**:
```json
{"timestamp": "...", "event_type": "safety_intervention", "tool": "rollback_manager.capture_state", "parameters": {"captured_state": {...}}}
{"timestamp": "...", "event_type": "action", "tool": "set_gpu_fan_percent", "parameters": {"requested_percent": 75.0}, "before_state": {...}, "after_state": {...}, "result": {"success": true}}
```

---

## 5. Modo de Simulación / Pruebas de Laboratorio

Para probar hipótesis sin hardware físico o en entornos de prueba:
* `--provider mock --mock-fault none`: Simula una RX 580 con respuesta normal y lineal.
* `--provider mock --mock-fault stuck_fan`: Simula exactamente el fallo reportado (tacómetro clavado en ~1127 RPM independientemente del porcentaje solicitado).
* `--provider mock --mock-fault no_fan_control`: Simula rechazo de escritura por parte del driver.

---

## 6. Pruebas Automatizadas

Para ejecutar la suite completa de tests:
```powershell
python -m unittest discover tests
```
