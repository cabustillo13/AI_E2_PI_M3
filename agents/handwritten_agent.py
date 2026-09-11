from typing import Dict, Any, List, Callable, Tuple
from openai import OpenAI


class HandwrittenReActAgent:
    """Demostración pedagógica del loop ReAct a mano sin framework."""
    def __init__(self, client: OpenAI, model: str, tools: Dict[str, Callable], max_steps: int = 5):
        self.client = client
        self.model = model
        self.tools = tools
        self.max_steps = max_steps

    def run(self, user_prompt: str, system_prompt: str) -> Tuple[str, List[Dict[str, Any]]]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        history = []
        step = 0

        while step < self.max_steps:
            step += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.0
                )
                output = response.choices[0].message.content or ""
                messages.append({"role": "assistant", "content": output})
                history.append({"step": step, "type": "thought", "content": output})

                if "FINAL_ANSWER:" in output:
                    return output.split("FINAL_ANSWER:")[-1].strip(), history

                if "ACTION:" in output and "ACTION_INPUT:" in output:
                    lines = output.split("\n")
                    action = [l for l in lines if "ACTION:" in l][0].replace("ACTION:", "").strip()
                    arg = [l for l in lines if "ACTION_INPUT:" in l][0].replace("ACTION_INPUT:", "").strip()

                    if action not in self.tools:
                        obs = f"Error recuperable: La herramienta '{action}' no existe."
                    else:
                        obs = self.tools[action](arg)

                    messages.append({"role": "user", "content": f"OBSERVATION: {obs}"})
                    history.append({"step": step, "type": "observation", "content": obs})
                else:
                    messages.append({"role": "user", "content": "Formato requerido: Usa ACTION/ACTION_INPUT o FINAL_ANSWER."})

            except Exception as e:
                err_msg = f"Error de ejecución recuperable: {str(e)}"
                history.append({"step": step, "type": "error", "content": err_msg})
                messages.append({"role": "user", "content": f"Sucedió un error: {err_msg}. Reintenta la acción."})

        return "Corte por Stopping Rule: Se ha excedido el presupuesto máximo de iteraciones.", history