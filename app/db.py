# app/db.py
"""
Módulo de banco de dados simples usando SQLite.
"""
import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Optional
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/tmp/app_ga.db")


def get_db_path() -> str:
    """Retorna o caminho do banco de dados."""
    return DB_PATH


@contextmanager
def get_db_connection():
    """
    Context manager para conexão com banco de dados.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Inicializa o banco de dados."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at TIMESTAMP
            )
        """)

        # Cria índices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_value ON items(value)")


def insert_items(count: int) -> int:
    """
    Insere itens no banco de dados.

    Args:
        count: Número de itens a inserir

    Returns:
        Número de itens inseridos
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for i in range(count):
            cursor.execute(
                "INSERT INTO items (name, value) VALUES (?, ?)",
                (f"item_{i}", i * 10)
            )
        return count


def query_items(limit: int = 100) -> List[Dict]:
    """
    Consulta itens do banco de dados.

    Args:
        limit: Limite de resultados

    Returns:
        Lista de itens
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items ORDER BY value DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def search_items(name_pattern: str) -> List[Dict]:
    """
    Busca itens por padrão de nome.

    Args:
        name_pattern: Padrão de busca (LIKE)

    Returns:
        Lista de itens encontrados
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE name LIKE ?", (f"%{name_pattern}%",))
        return [dict(row) for row in cursor.fetchall()]


def aggregate_values() -> Dict:
    """
    Agrega valores (SUM, AVG, COUNT).

    Returns:
        Dicionário com agregações
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as count,
                SUM(value) as sum,
                AVG(value) as avg,
                MIN(value) as min,
                MAX(value) as max
            FROM items
        """)
        row = cursor.fetchone()
        return dict(row)


# Inicializa banco na importação
init_db()


