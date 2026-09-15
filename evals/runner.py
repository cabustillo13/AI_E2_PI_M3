"""
Runner de evals de trayectoria.

Corre el dataset etiquetado (evals/dataset.jsonl) contra el grafo completo y mide:
  - Routing accuracy: ¿el orquestador clasificó el dominio esperado?
  - Tasa de éxito end-to-end: ¿la trayectoria completa (routing + agente/tool) resolvió
    la consulta sin errores?

Cada corrida queda agrupada en una sola "sesión" de Langfuse (una por ejecución del
runner) y cada caso individual queda scoreado en su propio trace vía `create_score`,
usando el `trace_id` que devuelve `orchestrator.run()`. Así la corrección de trayectorias
es navegable trace por trace en Langfuse, no solo un número en la terminal.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tabulate import tabulate

from langfuse import get_client
from langfuse.openai import OpenAI

from agents.rag_agents import DomainRAGAgents
from agents.orchestrator import NubbixHelpdeskGraph

# Cargar variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv()

_TICKET_ID_RE = re.compile(r"TICK-[A-Z0-9]+", re.IGNORECASE)


def _provision_real_ticket_id(orchestrator: NubbixHelpdeskGraph, session_id: str) -> str | None:
    """Crea un ticket REAL a través del propio pipeline del agente (create -> confirm
    vía interrupt -> MCP real) y devuelve el ID que efectivamente generó el server MCP.

    Esto reemplaza cualquier ID hardcodeado en el dataset: como `create_ticket` genera
    IDs aleatorios (uuid4), la única forma de tener un ID que exista de verdad en la DB
    es crearlo primero por el mismo camino que usaría un empleado real, y reusar el ID
    que la propia trayectoria devolvió.
    """
    thread_id = str(uuid.uuid4())
    out = orchestrator.run(
        "Crear ticket para: incidente de prueba generado por la suite de evals de trayectoria.",
        session_id=session_id,
        thread_id=thread_id,
    )
    if out.get("awaiting_confirmation"):
        out = orchestrator.resume(thread_id=thread_id, approved=True, session_id=session_id)

    match = _TICKET_ID_RE.search(out.get("response") or "")
    return match.group(0).upper() if match else None


def _is_e2e_success(case: dict, predicted_domain: str, response: str) -> bool:
    """Éxito end-to-end: ruteo correcto Y una respuesta válida (no vacía, sin error)."""
    if predicted_domain.lower() != case["expected_domain"].lower():
        return False
    if not response:
        return False
    if response.strip().lower().startswith(("error", "mcp error", "acción cancelada")):
        return False
    return True


def run_evals():
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    rag_agents = DomainRAGAgents(openai_client=client)
    orchestrator = NubbixHelpdeskGraph(openai_client=client, rag_agents=rag_agents)
    langfuse = get_client()

    eval_session_id = f"eval_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    dataset_path = Path(__file__).parent / "dataset.jsonl"
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f]

    correct_routes = 0
    e2e_successes = 0
    total_cases = len(cases)
    results_table = []

    for case in cases:
        query = case["query"]

        # Si el caso necesita un ticket_id real (consultas de "estado"), lo creamos
        # primero de verdad a través del propio agente y usamos el ID que devolvió
        # el server MCP. Nada hardcodeado: el ID sale de una trayectoria real.
        if case.get("requires_ticket_id"):
            real_ticket_id = _provision_real_ticket_id(orchestrator, eval_session_id)
            query = query.format(ticket_id=real_ticket_id or "TICK-INEXISTENTE")

        thread_id = str(uuid.uuid4())
        out = orchestrator.run(query, session_id=eval_session_id, thread_id=thread_id)

        # En modo batch (evals) no hay un humano para confirmar la creación de
        # tickets sensibles: se resuelve automáticamente el interrupt con
        # approved=True para poder medir la trayectoria end-to-end completa.
        if out.get("awaiting_confirmation"):
            out = orchestrator.resume(thread_id=thread_id, approved=True, session_id=eval_session_id)

        predicted = out.get("target_domain", "")
        response = out.get("response", "") or ""
        trace_id = out.get("trace_id")

        routing_ok = predicted.lower() == case["expected_domain"].lower()
        e2e_ok = _is_e2e_success(case, predicted, response)

        if routing_ok:
            correct_routes += 1
        if e2e_ok:
            e2e_successes += 1

        if trace_id:
            langfuse.create_score(trace_id=trace_id, name="routing_accuracy", value=routing_ok, data_type="BOOLEAN")
            langfuse.create_score(trace_id=trace_id, name="e2e_success", value=e2e_ok, data_type="BOOLEAN")

        results_table.append([
            case["id"],
            query[:40] + "...",
            case["expected_domain"],
            predicted,
            "SUCCESS" if routing_ok else "FAIL",
            "SUCCESS" if e2e_ok else "FAIL",
        ])

    routing_accuracy = (correct_routes / total_cases) * 100
    e2e_rate = (e2e_successes / total_cases) * 100

    print("\n--- REPORTE DE EVALUACIÓN DE TRAYECTORIAS M3 ---")
    print(tabulate(results_table, headers=["ID", "Consulta", "Esperado", "Obtenido", "Routing", "E2E"]))
    print(f"\nAccuracy de Routing: {routing_accuracy:.2f}% ({correct_routes}/{total_cases})")
    print(f"Tasa de Éxito End-to-End: {e2e_rate:.2f}% ({e2e_successes}/{total_cases})")
    print(f"\nSesión de Langfuse para esta corrida: {eval_session_id}")
    print("(buscala en Langfuse Cloud > Sessions para navegar cada trace individualmente)")

    langfuse.flush()


if __name__ == "__main__":
    run_evals()