import uuid
from fastmcp import FastMCP
from mcp_server.db import init_db, get_connection

mcp = FastMCP("Nubbix-Tickets-DB")
init_db()

@mcp.tool()
def create_ticket(employee_email: str, category: str, description: str) -> str:
    """Crea un nuevo ticket de soporte en la base de datos interna de Nubbix."""
    ticket_id = f"TICK-{uuid.uuid4().hex[:6].upper()}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tickets (ticket_id, employee_email, category, description, status) VALUES (?, ?, ?, ?, ?)",
        (ticket_id, employee_email, category, description, "OPEN")
    )
    conn.commit()
    conn.close()
    return f"Ticket registrado con éxito. ID: {ticket_id} | Estado: OPEN"

@mcp.tool()
def get_ticket_status(ticket_id: str) -> str:
    """Consulta el estado actual de un ticket registrado mediante su ID (ej. TICK-A1B2C3)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticket_id, category, description, status FROM tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return f"Error: No se encontró ningún ticket con el ID {ticket_id}."
    return f"Ticket ID: {row[0]} | Categoría: {row[1]} | Descripción: {row[2]} | Estado: {row[3]}"


if __name__ == "__main__":
    mcp.run()