from langfuse import observe
from langfuse.openai import OpenAI

from agents.retriever import DomainRetriever
from agents import mcp_client


class DomainRAGAgents:
    """Agentes especialistas HR, IT y Finance sobre el índice Chroma real de PIM2 + tools MCP."""

    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini", top_k: int = 3):
        self.client = openai_client
        self.model = model
        self.retriever = DomainRetriever(openai_client=openai_client, top_k=top_k)

    @observe(as_type="retriever", name="rag_hr_retrieve")
    def _context_hr(self, query: str) -> str:
        return self.retriever.build_context("hr", query)

    @observe(as_type="retriever", name="rag_it_retrieve")
    def _context_it(self, query: str) -> str:
        return self.retriever.build_context("it", query)

    @observe(as_type="retriever", name="rag_finance_retrieve")
    def _context_finance(self, query: str) -> str:
        return self.retriever.build_context("finance", query)

    @observe(as_type="agent", name="hr_agent")
    def run_hr_agent(self, query: str) -> str:
        context = self._context_hr(query)
        prompt = f"Eres el especialista de RRHH de Nubbix.\nContexto RAG (recuperado por relevancia a la consulta):\n{context}\n\nConsulta del empleado: {query}\nResponde de manera ejecutiva, citando la política si corresponde:"
        res = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return res.choices[0].message.content or ""

    @observe(as_type="agent", name="it_agent")
    def run_it_agent(self, query: str) -> str:
        context = self._context_it(query)
        prompt = f"Eres el especialista de IT de Nubbix.\nContexto RAG (recuperado por relevancia a la consulta):\n{context}\n\nConsulta del empleado: {query}\nResponde con instrucciones paso a paso:"
        res = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return res.choices[0].message.content or ""

    @observe(as_type="agent", name="finance_agent")
    def run_finance_agent(self, query: str) -> str:
        context = self._context_finance(query)
        prompt = f"Eres el especialista de Finanzas de Nubbix.\nContexto RAG (recuperado por relevancia a la consulta):\n{context}\n\nConsulta del empleado: {query}\nResponde con precisión de montos y procesos:"
        res = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return res.choices[0].message.content or ""

    @observe(as_type="tool", name="mcp_create_ticket")
    def mcp_create_ticket(self, employee_email: str, category: str, description: str) -> str:
        """Llama al server MCP real (mcp_server/server.py) vía protocolo MCP sobre stdio."""
        return mcp_client.create_ticket(employee_email, category, description)

    @observe(as_type="tool", name="mcp_get_ticket_status")
    def mcp_get_ticket_status(self, ticket_id: str) -> str:
        """Llama al server MCP real (mcp_server/server.py) vía protocolo MCP sobre stdio."""
        return mcp_client.get_ticket_status(ticket_id)