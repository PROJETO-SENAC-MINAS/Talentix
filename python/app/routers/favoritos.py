"""
CRUD de vagas favoritadas pelo candidato.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import exigir_tipo

router = APIRouter(prefix="/favoritos", tags=["Favoritos"])


class FavoritoCreate(BaseModel):
    id_vaga: str


async def _id_candidato(sessao: dict) -> str:
    candidato = await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if not candidato:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas candidatos podem favoritar vagas.")
    return candidato["ID_Candidatos"]


@router.post("", status_code=201)
async def favoritar_vaga(dados: FavoritoCreate, sessao: dict = Depends(exigir_tipo("candidato"))):
    id_candidato = await _id_candidato(sessao)
    existente = await fetch_one(
        "SELECT * FROM Favoritos_Vaga WHERE ID_Candidatos=%s AND ID_Vagas=%s", (id_candidato, dados.id_vaga)
    )
    if existente:
        return existente

    id_fav = novo_uuid()
    await execute(
        "INSERT INTO Favoritos_Vaga (ID_Favoritos_Vaga, ID_Candidatos, ID_Vagas) VALUES (%s, %s, %s)",
        (id_fav, id_candidato, dados.id_vaga),
    )
    return await fetch_one("SELECT * FROM Favoritos_Vaga WHERE ID_Favoritos_Vaga=%s", (id_fav,))


@router.get("")
async def listar_favoritos(sessao: dict = Depends(exigir_tipo("candidato"))):
    id_candidato = await _id_candidato(sessao)
    return await fetch_all(
        """SELECT fv.*, v.Titulo, v.Localizacao, v.Modalidade
           FROM Favoritos_Vaga fv
           JOIN Vagas v ON v.ID_Vagas = fv.ID_Vagas
           WHERE fv.ID_Candidatos=%s ORDER BY fv.CriadoEm DESC""",
        (id_candidato,),
    )


@router.delete("/{id_vaga}")
async def desfavoritar_vaga(id_vaga: str, sessao: dict = Depends(exigir_tipo("candidato"))):
    id_candidato = await _id_candidato(sessao)
    await execute(
        "DELETE FROM Favoritos_Vaga WHERE ID_Candidatos=%s AND ID_Vagas=%s", (id_candidato, id_vaga)
    )
    return {"mensagem": "Vaga removida dos favoritos."}