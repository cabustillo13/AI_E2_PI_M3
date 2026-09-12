"""
Loop ReAct escrito a mano, SIN framework.

Objetivo: entender qué hace LangGraph "gratis" antes de delegarle el control.
Implementa:
  - Loop Thought -> Action -> Observation contra la API de OpenAI directamente.
  - Memoria de corto plazo: la lista `messages` acumula todo el intercambio.
  - Stopping rule: presupuesto de pasos (`max_steps`).
  - Triage de errores: se distingue explícitamente entre errores RECUPERABLES
    (una tool que no existe, un argumento mal formado -> se le informa al LLM
    como observación y se le da otra oportunidad, con un presupuesto propio
    y más chico) y errores DUROS (falla de red/API -> se corta el loop de
    inmediato, no tiene sentido reintentar indefinidamente contra un error
    de infraestructura).
"""
import os
from typing import Dict, Callable

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

# Cargar variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv()


class RecoverableToolError(Exception):
    """Error de negocio: la tool pedida no existe o el argumento es inválido.
    Se informa al LLM como observación y se le deja reintentar."""


class HardAgentError(Exception):
    """Error de infraestructura (timeout, rate limit, 5xx). No se reintenta
    dentro del loop: se corta y se reporta hacia arriba."""


TOOLS: Dict[str, Callable[[], str]] = {
    "consultar_vacaciones": lambda: "Políticas Nubbix: corresponden 14 días corridos de vacaciones tras el primer año.",
    "consultar_wifi": lambda: "Manual IT Nubbix: la red corporativa es 'Nubbix-Corp', la contraseña rota mensualmente se solicita en el portal IT.",
    "consultar_reintegro": lambda: "Procesos de Finanzas Nubbix: los reintegros se cargan en ExpenseHub antes del día 25 de cada mes.",
}


def _execute_tool(action_name: str) -> str:
    if action_name not in TOOLS:
        # Error recuperable: la tool no existe. No abortamos el agente entero,
        # se lo hacemos saber al LLM como observación para que corrija el rumbo.
        raise RecoverableToolError(f"La herramienta '{action_name}' no existe. Tools disponibles: {list(TOOLS.keys())}")
    return TOOLS[action_name]()


class HandwrittenReActAgent:
    """Loop ReAct a mano sin framework, con stopping rules y triage de errores."""

    def __init__(self, client: OpenAI | None = None, max_steps: int = 4, max_recoverable_errors: int = 2):
        self.client = client or OpenAI()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.max_steps = max_steps
        self.max_recoverable_errors = max_recoverable_errors

    def run(self, user_query: str) -> str:
        sys_prompt = (
            "Eres el asistente de la mesa de ayuda de Nubbix.\n"
            f"Tools disponibles: {list(TOOLS.keys())}.\n"
            "Si necesitas una tool, responde EXACTAMENTE: ACTION: <nombre_tool>\n"
            "Si ya tenés la respuesta, respondé directamente al usuario de forma clara."
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_query},
        ]

        recoverable_errors = 0

        for step in range(1, self.max_steps + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0.0
                )
            except (APIError, APITimeoutError, RateLimitError) as e:
                # Error DURO: no tiene sentido seguir iterando contra la API.
                raise HardAgentError(f"Corte inmediato por error duro de infraestructura: {e}") from e

            output = response.choices[0].message.content or ""
            print(f"[Paso {step}] Salida LLM: {output}")

            if "ACTION:" not in output:
                return output

            action = output.split("ACTION:")[-1].strip()
            messages.append({"role": "assistant", "content": output})

            try:
                observation = _execute_tool(action)
            except RecoverableToolError as e:
                recoverable_errors += 1
                print(f"[Paso {step}] Error recuperable ({recoverable_errors}/{self.max_recoverable_errors}): {e}")
                if recoverable_errors >= self.max_recoverable_errors:
                    return "Corte por errores recuperables: se agotó el presupuesto de reintentos ante tools inválidas."
                messages.append({"role": "user", "content": f"OBSERVACIÓN (error recuperable): {e}"})
                continue

            print(f"[Paso {step}] Observación Tool: {observation}")
            messages.append({"role": "user", "content": f"OBSERVACIÓN: {observation}"})

        return "Corte por Stopping Rule: se superó el presupuesto máximo de pasos (posible loop sin convergencia)."


class _FakeLoopingClient:
    """Cliente OpenAI simulado (determinístico, sin red) que SIEMPRE pide la
    misma tool inexistente. Sirve para demostrar, de forma reproducible, que
    la stopping rule corta un loop que no converge."""

    def __init__(self):
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        msg = type("Msg", (), {"content": "ACTION: tool_que_no_existe"})
        choice = type("Choice", (), {"message": msg})
        return type("Resp", (), {"choices": [choice]})


if __name__ == "__main__":
    print("--- DEMO 1: AGENTE REACT A MANO (SIN FRAMEWORK, con LLM real) ---")
    agent = HandwrittenReActAgent(max_steps=4)
    resultado = agent.run("¿Cuántos días de vacaciones me corresponden en mi primer año?")
    print(f"\nResultado Final:\n{resultado}\n")

    print("\n--- DEMO 2: LOOP QUE NO CONVERGE (cliente simulado, sin red) ---")
    print("Muestra cómo la stopping rule corta un loop que pide siempre una tool inexistente.")
    stuck_agent = HandwrittenReActAgent(client=_FakeLoopingClient(), max_steps=3, max_recoverable_errors=5)
    resultado_stuck = stuck_agent.run("Consulta cualquiera")
    print(f"\nResultado Final (esperado: corte por stopping rule):\n{resultado_stuck}\n")