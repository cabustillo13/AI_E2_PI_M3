import json
import os
from pathlib import Path
from openai import OpenAI
from tabulate import tabulate
from agents.rag_agents import DomainRAGAgents
from agents.orchestrator import NubbixHelpdeskGraph

# Cargar variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv()


def run_evals():
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    rag_agents = DomainRAGAgents(openai_client=client)
    orchestrator = NubbixHelpdeskGraph(openai_client=client, rag_agents=rag_agents)

    dataset_path = Path(__file__).parent / "dataset.jsonl"
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f]

    correct_routes = 0
    total_cases = len(cases)
    results_table = []

    for case in cases:
        out = orchestrator.run(case["query"], approved=True)
        predicted = out["target_domain"]
        is_correct = predicted.lower() == case["expected_domain"].lower()
        if is_correct:
            correct_routes += 1

        results_table.append([
            case["id"],
            case["query"][:40] + "...",
            case["expected_domain"],
            predicted,
            "SUCCESS" if is_correct else "FAIL"
        ])

    accuracy = (correct_routes / total_cases) * 100

    print("\n--- REPORTE DE EVALUACIÓN DE TRAYECTORIAS M3 ---")
    print(tabulate(results_table, headers=["ID", "Consulta", "Esperado", "Obtenido", "Resultado"]))
    print(f"\nAccuracy de Routing: {accuracy:.2f}% ({correct_routes}/{total_cases})")
    print(f"Tasa de éxito End-to-End: {accuracy:.2f}%\n")


if __name__ == "__main__":
    run_evals()