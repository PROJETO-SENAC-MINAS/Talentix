"""Pool MySQL e transações de negócio compartilhadas por uma requisição."""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import logging
import aiomysql
from starlette.concurrency import run_in_threadpool
from app.core.config import settings

_pool: aiomysql.Pool | None = None
_connection: ContextVar = ContextVar("talentix_connection", default=None)
_callbacks: ContextVar = ContextVar("talentix_after_commit", default=None)
logger = logging.getLogger(__name__)


async def init_pool() -> None:
    global _pool
    # SELECTs isolados não podem deixar snapshots abertos no pool.
    _pool = await aiomysql.create_pool(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, db=settings.DB_NAME, autocommit=True,
        charset="utf8mb4", cursorclass=aiomysql.cursors.DictCursor,
        minsize=1, maxsize=10, pool_recycle=1800,
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> aiomysql.Pool:
    if _pool is None:
        raise RuntimeError("Pool de conexões não inicializado.")
    return _pool


@asynccontextmanager
async def connection():
    current = _connection.get()
    if current is not None:
        yield current
    else:
        async with get_pool().acquire() as conn:
            yield conn


@asynccontextmanager
async def transaction():
    """Todas as escritas de uma operação confirmam juntas ou sofrem rollback."""
    if _connection.get() is not None:
        yield
        return
    callbacks = []
    async with get_pool().acquire() as conn:
        await conn.begin()
        token = _connection.set(conn)
        callback_token = _callbacks.set(callbacks)
        try:
            yield
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
        finally:
            _callbacks.reset(callback_token)
            _connection.reset(token)
    # SMTP só ocorre depois do commit; falha externa não desfaz dados confirmados.
    for callback in callbacks:
        try:
            await run_in_threadpool(callback)
        except Exception:
            logger.exception("Falha ao enviar e-mail após a confirmação da operação.")


async def after_commit(callback):
    callbacks = _callbacks.get()
    if callbacks is not None:
        callbacks.append(callback)
    else:
        await run_in_threadpool(callback)


async def fetch_one(query: str, params: tuple | dict = ()) -> dict | None:
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        return await cur.fetchone()


async def fetch_all(query: str, params: tuple | dict = ()) -> list[dict]:
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        return list(await cur.fetchall())


async def execute(query: str, params: tuple | dict = ()) -> int:
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        return cur.rowcount


async def execute_returning_id(query: str, params: tuple | dict = ()) -> int:
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        return cur.lastrowid
