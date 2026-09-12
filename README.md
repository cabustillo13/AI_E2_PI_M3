# Nubbix Desk: Mesa de Ayuda Multi-Agente

Mesa de ayuda interna multi-agente construida sobre **LangGraph**, **Model Context Protocol (MCP)** y **Langfuse**. El sistema clasifica las intenciones de los empleados y las deriva a tres agentes RAG especializados (**HR**, **IT**, **Finance**) o a un servidor de herramientas **MCP** para la gestión de tickets en SQLite.

---

## Decisiones Técnicas Clave

- **LangGraph & Estado Tipado:** Se implementó un grafo de estado con `TypedDict` / `Pydantic` (`AgentState`) para gestionar el flujo de ejecución, contar iteraciones de forma determinística y activar banderas de interrupción.
- **Routing Económico & Prompt Dedicado:** La clasificación de intenciones corre sobre `gpt-4o-mini` con un prompt especializado de bajas latencias y costos mínimos, evaluado mediante coincidencias exactas (*exact match*).
- **Servidor MCP Propio:** Construido con `FastMCP` sobre SQLite para exponer las herramientas `create_ticket` y `get_ticket_status`, manteniendo la persistencia y separación de la capa de datos.
- **Human-in-the-Loop (Interrupts):** Las acciones sensibles (creación de tickets) requieren confirmación explícita del usuario mediante la interrupción del grafo antes de persistir cambios en la base de datos.
- **Stopping Rules e Iteración Acotada:** Presupuesto explícito de pasos por consulta (`max_steps=5`) para prevenir loops infinitos, derivaciones cíclicas o sobrecostos de API.
- **Trazabilidad y Evals en Langfuse Cloud:** Trazas end-to-end navegables por sesión y evaluación de trayectorias midiendo accuracy de routing y tasa de éxito end-to-end.

---

## Arquitectura del grafo

```text
               +-----------------------+
               |        Entrada        |
               +-----------------------+
                           |
                           v
               +-----------------------+
               |   Orquestador/Router  |
               +-----------------------+
                /      |       |      \
               /       |       |       \
              v        v       v        v
        +--------+ +--------+ +-------+ +------------+
        | HR RAG | | IT RAG | |Finance| | MCP Server |
        | Agent  | | Agent  | |  RAG  | | (Tickets)  |
        +--------+ +--------+ +-------+ +------------+
               \       |       |       /
                \      |       |      /
                 v     v       v     v
               +-----------------------+
               |        Estado /       |
               |    Respuesta Final    |
               +-----------------------+
```

---

## Estructura del Repositorio

```text
.
├── .env.example
├── requirements.txt
├── README.md
├── mcp_server/
│   ├── db.py               # Gestión centralizada de SQLite
│   ├── server.py           # Servidor MCP (FastMCP)
│   └── tickets.db          # Base de datos persistente
├── agents/
│   ├── handwritten_agent.py # Loop ReAct a mano (sin framework)
│   ├── rag_agents.py        # Agentes especialistas HR, IT, Finance
│   └── orchestrator.py      # Orquestador LangGraph + Routing + Interrupts
├── evals/
│   ├── dataset.jsonl       # Dataset de 25 casos de prueba etiquetados
│   └── runner.py           # Runner de evals de trayectoria
└── src/
    └── main.py             # Interfaz interactiva CLI
```

---

## Instalación y Configuración

### 1. Crear entorno virtual

```bash
python -m venv venv

# En Windows (PowerShell):
venv\Scripts\activate
# En Linux/macOS:
source venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Copia el archivo `.env.example` como `.env` y asigna tus claves API:

```bash
cp .env.example .env
```

Contenido del `.env`:

```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-mini
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

---

## Prototipo de Agente a Mano

El archivo `agents/handwritten_agent.py` representa el **prototipo conceptual sin framework**. 

### ¿Por qué existe y cuál es su rol?
1. **Comprensión del Loop ReAct:** Implementa a mano el ciclo *Thought -> Action -> Observation* directamente contra la API de OpenAI sin abstraer el control en una librería.
2. **Manejo de Errores y Stopping Rules:** Demuestra cómo capturar excepciones recuperables y forzar el corte por límite de pasos desde código nativo.
3. **Paso previo a LangGraph:** Sirve como base comparativa para justificar la migración del agente imperativo a un grafo de estado declarativo (`orchestrator.py`).

Para ejecutar una prueba aislada del agente a mano sin framework:
```bash
python -m agents.handwritten_agent
```

Ejemplo de salida de consola:

```text
--- DEMO AGENTE REACT A MANO (SIN FRAMEWORK) ---
[Paso 1] Salida LLM: ACTION: consultar_vacaciones
[Paso 1] Observación Tool: Políticas Nubbix: Corresponden 14 días corridos de vacaciones tras el primer año.
[Paso 2] Salida LLM: En tu primer año en Nubbix, te corresponden 14 días corridos de vacaciones.

Resultado Final:
En tu primer año en Nubbix, te corresponden 14 días corridos de vacaciones.
```

---

## Resultados de Evaluación de Trayectoria

La suite de evaluadores verifica el routing por intención y la tasa de resolución end-to-end contra un dataset etiquetado de 25 consultas reales de empleados.

```bash
python -m evals.runner
```

### Reporte de Métricas

| ID | Consulta | Esperado | Obtenido | Resultado |
|----|----------|----------|----------|-----------|
| 1 | ¿Cuántos días de vacaciones me correspon... | HR | HR | SUCCESS |
| 2 | ¿Cómo solicito la licencia por maternida... | HR | HR | SUCCESS |
| 3 | ¿Cuál es la política de trabajo remoto e... | HR | HR | SUCCESS |
| 4 | ¿Cómo accedo a los descuentos en gimnasi... | HR | HR | SUCCESS |
| 5 | ¿Qué documentación debo presentar para j... | HR | HR | SUCCESS |
| 6 | ¿Cuándo se realiza la evaluación de dese... | HR | HR | SUCCESS |
| 7 | Olvidé la contraseña de mi cuenta instit... | IT | IT | SUCCESS |
| 8 | ¿Cómo me conecto a la VPN de la empresa ... | IT | IT | SUCCESS |
| 9 | Mi laptop no enciende y necesito asisten... | IT | IT | SUCCESS |
| 10 | ¿Cuál es el procedimiento para solicitar... | IT | IT | SUCCESS |
| 11 | ¿Qué software está autorizado para insta... | IT | IT | SUCCESS |
| 12 | No puedo conectarme a la red WiFi de la ... | IT | IT | SUCCESS |
| 13 | ¿Cuál es el tope máximo de reembolso par... | Finance | Finance | SUCCESS |
| 14 | ¿Cómo rindo los gastos de un viaje corpo... | Finance | Finance | SUCCESS |
| 15 | ¿Qué día del mes se deposita el sueldo?... | Finance | Finance | SUCCESS |
| 16 | ¿Cómo solicito el comprobante de retenci... | Finance | Finance | SUCCESS |
| 17 | ¿Cuál es el formato requerido para carga... | Finance | Finance | SUCCESS |
| 18 | Necesito solicitar un adelanto de viátic... | Finance | Finance | SUCCESS |
| 19 | Por favor quiero crear ticket para cambi... | Ticket | IT | FAIL |
| 20 | Crear ticket para solicitar acceso a la ... | Ticket | Ticket | SUCCESS |
| 21 | ¿Cuál es el estado del ticket TICK-8A9B2... | Ticket | Ticket | SUCCESS |
| 22 | Quiero consultar estado del ticket TICK-... | Ticket | Ticket | SUCCESS |
| 23 | Crear ticket por falla en el sistema de ... | Ticket | Ticket | SUCCESS |
| 24 | Por favor crear ticket para configurar m... | Ticket | Ticket | SUCCESS |
| 25 | Consultar estado del ticket TICK-F4E3D2... | Ticket | Ticket | SUCCESS |

**Accuracy de Routing:** 96.00% (24/25)  
**Tasa de Éxito End-to-End:** 96.00%

---

## Ejecución del Servicio Interactive CLI

Para interactuar con el sistema multi-agente en tiempo real:

```bash
python -m src.main
```

Ejemplo de salida de consola:

```text
Mesa de Ayuda Multi-Agente Nubbix
Escriba 'salir' para terminar.

Empleado: mi laptop no enciende

[Orquestador] Intención detectada: IT
[Agente Especialista] Respuesta:
Claro, aquí tienes las instrucciones paso a paso para resolver el problema de tu laptop que no enciende:

### Instrucciones para solucionar el problema de la laptop que no enciende

1. **Verifica la conexión de energía:**
   - Asegúrate de que el adaptador de corriente esté correctamente conectado a la laptop y a la toma de corriente.
   - Comprueba que la luz indicadora del adaptador de corriente esté encendida. Si no está encendida, prueba con otra toma de corriente.

2. **Revisa la batería:**
   - Si tu laptop tiene una batería extraíble, apágala, desconéctala de la corriente, retira la batería y vuelve a colocarla. Luego, intenta encenderla nuevamente.
   - Si la batería no es extraíble, asegúrate de que esté bien conectada.

3. **Realiza un reinicio forzado:**
   - Mantén presionado el botón de encendido durante al menos 10-15 segundos. Esto puede ayudar a reiniciar el hardware.
   - Después de soltar el botón, espera unos segundos y vuelve a intentar encender la laptop.

4. **Conecta un monitor externo (opcional):**
   - Si tienes un monitor externo disponible, conéctalo a la laptop para verificar si el problema está relacionado con la pantalla. Si el monitor externo muestra la imagen, el problema podría ser la pantalla de la laptop.

5. **Escucha los sonidos:**
   - Presta atención a cualquier sonido que haga la laptop al intentar encenderla (como ventiladores o pitidos). Esto puede indicar un problema específico.

6. **Si la laptop sigue sin encender:**
   - Si después de seguir estos pasos la laptop no enciende, es posible que necesites asistencia técnica.
   - Notifica inmediatamente al canal de Slack #it-ops y envía un email a it@nubbix.com para reportar el problema.

7. **Documenta el problema:**
   - Anota cualquier mensaje de error o comportamiento inusual que hayas notado al intentar encender la laptop. Esto será útil para el equipo de IT.

Recuerda que si tu laptop presenta daños físicos evidentes, como golpes o caídas, es importante mencionarlo al equipo de IT.
```