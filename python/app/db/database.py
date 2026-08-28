"""
Gerenciamento do pool de conexões MySQL (SQL puro, via aiomysql).
Nenhum ORM é utilizado — todas as queries são escritas manualmente.
"""
import aiomysql
from app.core.config import settings

_pool: aiomysql.Pool | None = None


async def init_pool() -> None:
    global _pool
    _pool = await aiomysql.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        autocommit=False,
        cursorclass=aiomysql.cursors.DictCursor,
        minsize=1,
        maxsize=10,
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> aiomysql.Pool:
    if _pool is None:
        raise RuntimeError("Pool de conexões não inicializado. Chame init_pool() no startup.")
    return _pool


async def fetch_one(query: str, params: tuple | dict = ()) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()


async def fetch_all(query: str, params: tuple | dict = ()) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()


async def execute(query: str, params: tuple | dict = ()) -> int:
    """Executa INSERT/UPDATE/DELETE e retorna o número de linhas afetadas."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            await conn.commit()
            return cur.rowcount


async def execute_returning_id(query: str, params: tuple | dict = ()) -> int:
    """Executa INSERT e retorna lastrowid (útil para tabelas com AUTO_INCREMENT)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            await conn.commit()
            return cur.lastrowid