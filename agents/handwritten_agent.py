import os
from openai import OpenAI

# Cargar variables de entorno desde el archivo .env
from dotenv import load_dotenv
load_dotenv()


class HandwrittenReActAgent:
    """Loop ReAct a mano sin framework."""

    def __init__(self, max_steps: int = 3):
        self.client = OpenAI()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.max_steps = max_steps

    def _execute_tool(self, action_name: str) -> str:
        """Ejecución de herramientas del agente."""
        tools = {
            "consultar_vacaciones": "Políticas Nubbix: Corresponden 14 días corridos de vacaciones tras el primer año."
        }
        return tools.get(action_name, f"Error recuperable: La herramienta '{action_name}' no existe.")

    def run(self, user_query: str) -> str:
        sys_prompt = (
            "Eres el asistente de RRHH de Nubbix.\n"
            "Si necesitas consultar la política de vacaciones responde exactamente: ACTION: consultar_vacaciones\n"
            "Si ya tienes la respuesta, responde directamente al usuario de forma clara."
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_query}
        ]

        for step in range(1, self.max_steps + 1):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0
            )
            output = response.choices[0].message.content or ""
            print(f"[Paso {step}] Salida LLM: {output}")

            if "ACTION:" not in output:
                return output

            action = output.split("ACTION:")[-1].strip()
            observation = self._execute_tool(action)
            print(f"[Paso {step}] Observación Tool: {observation}")

            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": f"OBSERVACIÓN: {observation}"})

        return "Corte por Stopping Rule: Se superó el presupuesto máximo de pasos."


if __name__ == "__main__":
    print("--- DEMO AGENTE REACT A MANO (SIN FRAMEWORK) ---")
    agent = HandwrittenReActAgent(max_steps=3)
    resultado = agent.run("¿Cuántos días de vacaciones me corresponden en mi primer año?")
    print(f"\nResultado Final:\n{resultado}\n")