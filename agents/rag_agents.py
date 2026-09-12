from pathlib import Path
from openai import OpenAI
from mcp_server.db import init_db, get_connection


class DomainRAGAgents:
    """Agentes especialistas en dominios HR, IT y Finance utilizando corpus RAG de PI Módulo 2."""
    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
        init_db()

    def _get_corpus_context(self, domain: str) -> str:
        base_dir = Path(__file__).parent.parent / "data" / "corpus"
        files = {
            "hr": base_dir / "hr_policies.md",
            "it": base_dir / "it_manual.md",
            "finance": base_dir / "finance_processes.md"
        }
        target_file = files.get(domain.lower())
        if target_file and target_file.exists():
            return target_file.read_text(encoding="utf-8")[:1500]
        return f"Políticas e información general del área de {domain.upper()}."

    def run_hr_agent(self, query: str) -> str:
        context = self._get_corpus_context("hr")
        prompt = f"Eres el especialista de RRHH de Nubbix.\nContexto RAG:\n{context}\n\nConsulta del empleado: {query}\nResponde de manera ejecutiva:"
        res = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return res.choices[0].message.content or ""

    def run_it_agent(self, query: str) -> str:
        context = self._get_corpus_context("it")
        prompt = f"Eres el especialista de IT de Nubbix.\nContexto RAG:\n{context}\n\nConsulta del empleado: {query}\nResponde con instrucciones paso a paso:"
        res = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return res.choices[0].message.content or ""

    def run_finance_agent(self, query: str) -> str:
        context = self._get_corpus_context("finance")
        prompt = f"Eres el especialista de Finanzas de Nubbix.\nContexto RAG:\n{context}\n\nConsulta del empleado: {query}\nResponde con precisión de montos y procesos:"
        res = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return res.choices[0].message.content or ""

    def execute_mcp_tool(self, tool_name: str, args: dict) -> str:
        """Conexión cliente con la base de datos MCP de tickets."""
        conn = get_connection()
        cursor = conn.cursor()
        if tool_name == "create_ticket":
            import uuid
            ticket_id = f"TICK-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute(
                "INSERT INTO tickets (ticket_id, employee_email, category, description, status) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, args.get("employee_email", "empleado@nubbix.com"), args.get("category", "IT"), args.get("description", "Ticket de soporte"), "OPEN")
            )
            conn.commit()
            conn.close()
            return f"Ticket creado con éxito por MCP. ID: {ticket_id} (Estado: OPEN)"
        elif tool_name == "get_ticket_status":
            cursor.execute("SELECT ticket_id, category, description, status FROM tickets WHERE ticket_id = ?", (args.get("ticket_id"),))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return f"MCP error: El ticket {args.get('ticket_id')} no existe."
            return f"Estado del ticket {row[0]}: {row[3]} ({row[1]} - {row[2]})"
        conn.close()
        return "Herramienta no encontrada."