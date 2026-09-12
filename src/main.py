import os
import uuid

from langfuse import get_client
from langfuse.openai import OpenAI

from agents.rag_agents import DomainRAGAgents
from agents.orchestrator import NubbixHelpdeskGraph

# Cargar variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv()


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: registrá tu OPENAI_API_KEY en el archivo .env")
        return

    client = OpenAI(api_key=api_key)
    rag_agents = DomainRAGAgents(openai_client=client)
    orchestrator = NubbixHelpdeskGraph(openai_client=client, rag_agents=rag_agents)

    # Todas las consultas de esta corrida de CLI quedan agrupadas bajo la misma
    # sesión de Langfuse, para poder revisar la conversación completa de punta a punta.
    cli_session_id = f"cli_session_{uuid.uuid4().hex[:8]}"

    print("Mesa de Ayuda Multi-Agente Nubbix")
    print("Escriba 'salir' para terminar.\n")

    while True:
        query = input("Empleado: ").strip()
        if query.lower() in ["salir", "exit"]:
            break
        if not query:
            continue

        thread_id = str(uuid.uuid4())
        result = orchestrator.run(query, session_id=cli_session_id, thread_id=thread_id)

        # --- Human-in-the-loop real: el grafo se pausó en un interrupt() ---
        if result.get("awaiting_confirmation"):
            preview = result["interrupt"].get("preview", "Se ejecutará una acción sensible.")
            print(f"\n[Confirmación requerida] {preview}")
            confirm = input("¿Confirmás la acción? (s/n): ").strip().lower()
            approved = confirm in ["s", "si", "sí", "y", "yes"]
            result = orchestrator.resume(thread_id=thread_id, approved=approved, session_id=cli_session_id)

        print(f"\n[Orquestador] Intención detectada: {result.get('target_domain')}")
        print(f"[Agente Especialista] Respuesta:\n{result.get('response')}\n")

    get_client().flush()


if __name__ == "__main__":
    main()