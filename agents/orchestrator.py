from typing import Dict, Any, TypedDict, Literal
from langgraph.graph import StateGraph, END
from openai import OpenAI


class AgentState(TypedDict):
    user_query: str
    target_domain: str
    response: str
    steps_count: int
    max_steps: int
    require_human_approval: bool
    approved: bool


class NubbixHelpdeskGraph:
    """Orquestador LangGraph con routing por intención y stopping rules."""
    def __init__(self, openai_client: OpenAI, rag_agents, model: str = "gpt-4o-mini", max_steps: int = 5):
        self.client = openai_client
        self.rag_agents = rag_agents
        self.model = model
        self.max_steps = max_steps
        self.graph = self._build_graph()

    def _router_node(self, state: AgentState) -> AgentState:
        state["steps_count"] = state.get("steps_count", 0) + 1
        if state["steps_count"] > state["max_steps"]:
            state["response"] = "Parada de seguridad: Presupuesto máximo de pasos superado."
            return state

        prompt = f"""Eres el Orquestador de la Mesa de Ayuda de Nubbix.
        Clasifica la consulta del empleado estrictamente en una de las siguientes intenciones:
        - HR: Consultas de vacaciones, licencias, beneficios, políticas de RRHH.
        - IT: Configuración, VPN, contraseñas, hardware, red, software.
        - Finance: Reintegros, facturación, viáticos, reembolsos, sueldos.
        - Ticket: Crear o consultar explícitamente el estado de un ticket.

        Consulta: "{state['user_query']}"
        Responde ÚNICAMENTE con una palabra: HR, IT, Finance, o Ticket.
        """
        res = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        domain = res.choices[0].message.content.strip()
        if domain not in ["HR", "IT", "Finance", "Ticket"]:
            domain = "IT"

        state["target_domain"] = domain
        if "crear ticket" in state["user_query"].lower():
            state["require_human_approval"] = True
        return state

    def _hr_node(self, state: AgentState) -> AgentState:
        state["response"] = self.rag_agents.run_hr_agent(state["user_query"])
        return state

    def _it_node(self, state: AgentState) -> AgentState:
        state["response"] = self.rag_agents.run_it_agent(state["user_query"])
        return state

    def _finance_node(self, state: AgentState) -> AgentState:
        state["response"] = self.rag_agents.run_finance_agent(state["user_query"])
        return state

    def _ticket_mcp_node(self, state: AgentState) -> AgentState:
        q = state["user_query"].lower()
        if "crear ticket" in q:
            if state.get("require_human_approval") and not state.get("approved", False):
                state["response"] = "ACCIÓN SENSIBLE (Human-in-the-Loop): Requiere confirmación explícita. Reenvíe con aprobación."
                return state
            res = self.rag_agents.execute_mcp_tool("create_ticket", {
                "employee_email": "empleado@nubbix.com",
                "category": "IT",
                "description": state["user_query"]
            })
        else:
            words = state["user_query"].split()
            ticket_id = next((w for w in words if "TICK-" in w), "TICK-10001")
            res = self.rag_agents.execute_mcp_tool("get_ticket_status", {"ticket_id": ticket_id})

        state["response"] = res
        return state

    def _route_decision(self, state: AgentState) -> Literal["hr", "it", "finance", "ticket", "end"]:
        if "Parada de seguridad" in state.get("response", ""):
            return "end"
        domain = state.get("target_domain", "").lower()
        return domain if domain in ["hr", "it", "finance", "ticket"] else "it"

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("router", self._router_node)
        workflow.add_node("hr", self._hr_node)
        workflow.add_node("it", self._it_node)
        workflow.add_node("finance", self._finance_node)
        workflow.add_node("ticket", self._ticket_mcp_node)

        workflow.set_entry_point("router")
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {"hr": "hr", "it": "it", "finance": "finance", "ticket": "ticket", "end": END}
        )

        workflow.add_edge("hr", END)
        workflow.add_edge("it", END)
        workflow.add_edge("finance", END)
        workflow.add_edge("ticket", END)

        return workflow.compile()

    def run(self, user_query: str, approved: bool = False) -> Dict[str, Any]:
        return self.graph.invoke({
            "user_query": user_query,
            "target_domain": "",
            "response": "",
            "steps_count": 0,
            "max_steps": self.max_steps,
            "require_human_approval": False,
            "approved": approved
        })