import os
from openai import OpenAI
from agents.rag_agents import DomainRAGAgents
from agents.orchestrator import NubbixHelpdeskGraph

# Cargar variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv()


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: Registre su OPENAI_API_KEY en el archivo .env")
        return

    client = OpenAI(api_key=api_key)
    rag_agents = DomainRAGAgents(openai_client=client)
    orchestrator = NubbixHelpdeskGraph(openai_client=client, rag_agents=rag_agents)

    print("Mesa de Ayuda Multi-Agente Nubbix")
    print("Escriba 'salir' para terminar.\n")

    while True:
        query = input("Empleado: ").strip()
        if query.lower() in ["salir", "exit"]:
            break
        if not query:
            continue

        result = orchestrator.run(query, approved=False)
        print(f"\n[Orquestador] Intención detectada: {result['target_domain']}")
        print(f"[Agente Especialista] Respuesta:\n{result['response']}\n")


if __name__ == "__main__":
    main()