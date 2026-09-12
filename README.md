# Nubbix Desk: Mesa de Ayuda Multi-Agente

Mesa de ayuda interna multi-agente construida con **LangGraph**, **MCP (Model Context Protocol)** y **Langfuse**. El sistema clasifica las intenciones de los empleados y las deriva a agentes especializados en **HR**, **IT**, **Finance** o acciones sobre la **Base de Datos de Tickets**.

---

## Arquitectura y Decisiones Técnicas

- **LangGraph & Estado Tipado:** Se definió un estado estructurado (AgentState) que transporta el conteo de iteraciones y banderas de interrupción.

- **Stopping Rules:** Control estricto de presupuesto máximo de pasos (max_steps=5) para prevenir loops infinitos o consumo excesivo de tokens.

- **Servidor MCP:** Implementado con FastMCP sobre una base de datos SQLite persistente para ejecutar las herramientas create_ticket y get_ticket_status.

- **Human-in-the-Loop:** Las acciones sensibles (creación de tickets) solicitan confirmación previa antes de su ejecución definitiva en la base de datos.

- **Trazabilidad:** Integración nativa para la inspección y depuración de trazas end-to-end en Langfuse.

## Arquitectura del grafo

```text
               +-----------------------+
               |      Entrada          |
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
               |     Respuesta Final   |
               +-----------------------+
```

---

## Estructura del Repositorio

```text
├── .env.example
├── requirements.txt
├── README.md
├── mcp_server/
│   └── server.py
├── agents/
│   ├── handwritten_agent.py
│   ├── rag_agents.py
│   └── orchestrator.py
├── evals/
│   ├── dataset.jsonl
│   └── runner.py
└── main.py
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

## Evaluaciones

Ejecutar la suite de evaluaciones de trayectoria:

```bash
python -m evals.runner
```

---

## Ejecución del Servicio

Iniciar la aplicación interactiva:

```bash
python -m src.main
```
