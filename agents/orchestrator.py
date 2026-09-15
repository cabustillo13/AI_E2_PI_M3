import re
import uuid
from typing import Dict, Any, TypedDict, Literal, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from langfuse import observe, get_client, propagate_attributes
from langfuse.openai import OpenAI

# Regex de intención de acción sobre tickets.
_CREATE_TICKET_RE = re.compile(
    r"\b(crear|generar|abrir|solicitar)\b.{0,15}\bticket\b", re.IGNORECASE
)
_TICKET_ID_RE = re.compile(r"TICK-[A-Z0-9]+", re.IGNORECASE)

VALID_DOMAINS = ["HR", "IT", "Finance", "Ticket"]


class AgentState(TypedDict):
    user_query: str
    target_domain: str
    response: str
    steps_count: int
    max_steps: int
    action_type: Optional[str]        # "create" | "status" | None
    require_human_approval: bool
    approved: bool


class NubbixHelpdeskGraph:
    """Orquestador LangGraph: routing por intención, stopping rules, HITL con interrupt() y checkpointer."""

    def __init__(self, openai_client: OpenAI, rag_agents, model: str = "gpt-4o-mini", max_steps: int = 5):
        self.client = openai_client
        self.rag_agents = rag_agents
        self.model = model
        self.max_steps = max_steps
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    # ------------------------------------------------------------------ #
    # Nodos del grafo
    # ------------------------------------------------------------------ #

    @observe(as_type="chain", name="router_node")
    def _router_node(self, state: AgentState) -> AgentState:
        state["steps_count"] = state.get("steps_count", 0) + 1
        if state["steps_count"] > state["max_steps"]:
            state["response"] = "Parada de seguridad: presupuesto máximo de pasos superado."
            state["target_domain"] = "END"
            return state

        # Prompt de routing separado del de respuesta (se evalúan e iteran por separado).
        # Regla de prioridad explícita + few-shot para evitar que el LLM confunda el
        # *tema* del ticket (IT/HR/Finance) con la *intención* de gestionar un ticket.
        prompt = f"""Eres el Orquestador de la Mesa de Ayuda de Nubbix.
        Clasifica la consulta del empleado en UNA sola intención: HR, IT, Finance o Ticket.

        REGLA DE PRIORIDAD (aplicarla SIEMPRE primero): si la consulta pide explícitamente
        crear/abrir/generar un ticket, o consultar el estado de un ticket, la intención es
        "Ticket" — sin importar de qué tema hable el ticket (IT, HR o Finance).

        Ejemplos:
        - "Mi laptop no enciende" -> IT (no pide ticket, es soporte directo)
        - "Quiero crear un ticket para cambiar mi contraseña" -> Ticket (pide crear ticket, aunque el tema sea IT)
        - "¿Cuál es el estado del ticket TICK-8A9B2?" -> Ticket
        - "¿Cuántos días de vacaciones tengo?" -> HR
        - "¿Cuál es el tope de reembolso de viáticos?" -> Finance
        - "¿Qué día del mes se deposita el sueldo?" -> Finance (pagos y fechas de depósito son Finance, aunque el sueldo en sí sea un tema de RRHH)

        Consulta: "{state['user_query']}"
        Responde ÚNICAMENTE con una palabra: HR, IT, Finance o Ticket.
        """
        res = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        domain = (res.choices[0].message.content or "").strip()
        if domain not in VALID_DOMAINS:
            domain = "IT"

        state["target_domain"] = domain

        if domain == "Ticket":
            if _CREATE_TICKET_RE.search(state["user_query"]):
                state["action_type"] = "create"
                state["require_human_approval"] = True
            else:
                state["action_type"] = "status"

        get_client().update_current_span(metadata={"target_domain": domain, "steps_count": state["steps_count"]})
        return state

    @observe(as_type="agent", name="hr_node")
    def _hr_node(self, state: AgentState) -> AgentState:
        state["response"] = self.rag_agents.run_hr_agent(state["user_query"])
        return state

    @observe(as_type="agent", name="it_node")
    def _it_node(self, state: AgentState) -> AgentState:
        state["response"] = self.rag_agents.run_it_agent(state["user_query"])
        return state

    @observe(as_type="agent", name="finance_node")
    def _finance_node(self, state: AgentState) -> AgentState:
        state["response"] = self.rag_agents.run_finance_agent(state["user_query"])
        return state

    @observe(as_type="tool", name="ticket_node")
    def _ticket_mcp_node(self, state: AgentState) -> AgentState:
        if state.get("action_type") == "create":
            # --- Human-in-the-loop real: interrupt() del grafo, no un `if` manual. ---
            # Esto SUSPENDE la ejecución del grafo (con el checkpointer persistiendo
            # el estado) hasta que quien llama al grafo resuelva con
            # graph.invoke(Command(resume=True/False), config={thread_id: ...}).
            if state.get("require_human_approval") and not state.get("approved"):
                decision = interrupt({
                    "type": "confirm_sensitive_action",
                    "action": "create_ticket",
                    "preview": f"Se creará un ticket de soporte con la descripción: \"{state['user_query']}\"",
                })
                state["approved"] = bool(decision)

            if not state.get("approved"):
                state["response"] = "Acción cancelada: el usuario no confirmó la creación del ticket."
                return state

            state["response"] = self.rag_agents.mcp_create_ticket(
                employee_email="empleado@nubbix.com",
                category="IT",
                description=state["user_query"],
            )
        else:
            match = _TICKET_ID_RE.search(state["user_query"])
            ticket_id = match.group(0).upper() if match else "TICK-00000"
            state["response"] = self.rag_agents.mcp_get_ticket_status(ticket_id)
        return state

    def _route_decision(self, state: AgentState) -> Literal["hr", "it", "finance", "ticket", "end"]:
        domain = state.get("target_domain", "")
        mapping = {"HR": "hr", "IT": "it", "Finance": "finance", "Ticket": "ticket"}
        return mapping.get(domain, "end")

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
            {"hr": "hr", "it": "it", "finance": "finance", "ticket": "ticket", "end": END},
        )

        workflow.add_edge("hr", END)
        workflow.add_edge("it", END)
        workflow.add_edge("finance", END)
        workflow.add_edge("ticket", END)

        return workflow.compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------ #
    # API pública: run() arranca un thread, resume() responde a un interrupt
    # ------------------------------------------------------------------ #

    @observe(name="orchestrator_run", as_type="agent")
    def run(self, user_query: str, session_id: Optional[str] = None, thread_id: Optional[str] = None) -> Dict[str, Any]:
        thread_id = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        with propagate_attributes(session_id=session_id or thread_id, tags=["nubbix-helpdesk"]):
            result = self.graph.invoke(
                {
                    "user_query": user_query,
                    "target_domain": "",
                    "response": "",
                    "steps_count": 0,
                    "max_steps": self.max_steps,
                    "action_type": None,
                    "require_human_approval": False,
                    "approved": False,
                },
                config=config,
            )

        trace_id = get_client().get_current_trace_id()

        if "__interrupt__" in result:
            interrupt_payload = result["__interrupt__"][0].value
            return {
                "thread_id": thread_id,
                "trace_id": trace_id,
                "awaiting_confirmation": True,
                "interrupt": interrupt_payload,
                "target_domain": "Ticket",
                "response": None,
            }

        result["thread_id"] = thread_id
        result["trace_id"] = trace_id
        result["awaiting_confirmation"] = False
        return result

    @observe(name="orchestrator_resume", as_type="agent")
    def resume(self, thread_id: str, approved: bool, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Resuelve un interrupt pendiente (confirmación humana) y continúa la ejecución del grafo."""
        config = {"configurable": {"thread_id": thread_id}}
        with propagate_attributes(session_id=session_id or thread_id, tags=["nubbix-helpdesk", "resume"]):
            result = self.graph.invoke(Command(resume=approved), config=config)

        trace_id = get_client().get_current_trace_id()
        result["thread_id"] = thread_id
        result["trace_id"] = trace_id
        result["awaiting_confirmation"] = False
        return result