"""Operações HTTP de escrita usam uma única transação, inclusive notificações."""
from fastapi import APIRouter
from fastapi.routing import APIRoute
from app.db import database


class TransactionRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def transactional_handler(request):
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                async with database.transaction():
                    return await handler(request)
            return await handler(request)

        return transactional_handler


class AtomicRouter(APIRouter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("route_class", TransactionRoute)
        super().__init__(*args, **kwargs)
