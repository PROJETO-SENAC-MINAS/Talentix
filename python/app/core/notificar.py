"""
Helper central de notificações: toda vez que o sistema precisa avisar um
usuário, esta função grava a notificação in-app (tabela Notificacoes) E
dispara o e-mail correspondente, mantendo os dois canais sempre sincronizados.
"""
from app.db.database import fetch_one, execute
from app.core.security import novo_uuid


async def notificar_usuario(id_usuario: str, titulo: str, mensagem: str, tipo: str, enviar_email_fn=None) -> None:
    """
    Cria o registro em Notificacoes e, se enviar_email_fn for passado,
    dispara o e-mail correspondente usando o e-mail cadastrado do usuário.
    enviar_email_fn deve ser uma função sem argumentos (já com os dados
    "presos" via lambda/closure) que retorna bool.
    """
    id_notif = novo_uuid()
    await execute(
        """INSERT INTO Notificacoes (ID_Notificacoes, ID_Usuarios, Titulo, Mensagem, Tipo)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_notif, id_usuario, titulo, mensagem, tipo),
    )

    if enviar_email_fn is not None:
        usuario = await fetch_one("SELECT Email FROM Usuarios WHERE ID_Usuarios=%s", (id_usuario,))
        if usuario and usuario["Email"]:
            enviar_email_fn(usuario["Email"])