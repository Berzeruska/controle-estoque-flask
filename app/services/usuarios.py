"""Regras de autenticação e de gestão de usuários."""
from __future__ import annotations

import re
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import Papel, Usuario, agora_utc

# Hash de uma senha qualquer, usado quando o e-mail não existe. Conferir uma
# senha contra ele gasta o mesmo tempo que conferir contra um usuário real,
# de modo que o tempo de resposta não revela quais e-mails estão cadastrados
# (ataque de enumeração por tempo — "timing attack").
_HASH_FICTICIO = generate_password_hash("senha-ficticia-para-equalizar-tempo")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErroAutenticacao(Exception):
    pass


class ErroValidacao(ValueError):
    pass


def validar_senha(senha: str) -> None:
    if len(senha) < 8:
        raise ErroValidacao("A senha precisa ter ao menos 8 caracteres.")
    if not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        raise ErroValidacao("A senha precisa ter letras e números.")


def criar_usuario(nome: str, email: str, senha: str, papel: Papel = Papel.OPERADOR) -> Usuario:
    nome = (nome or "").strip()
    email = (email or "").strip().lower()
    if not nome:
        raise ErroValidacao("Informe o nome.")
    if not EMAIL_RE.match(email):
        raise ErroValidacao("E-mail inválido.")
    if db.session.scalar(db.select(Usuario).filter_by(email=email)):
        raise ErroValidacao("Já existe um usuário com esse e-mail.")
    validar_senha(senha or "")

    usuario = Usuario(nome=nome, email=email, papel=papel)
    usuario.definir_senha(senha)
    db.session.add(usuario)
    db.session.commit()
    return usuario


def autenticar(email: str, senha: str) -> Usuario:
    """Devolve o usuário se as credenciais conferirem; senão lança ErroAutenticacao.

    A mensagem de erro é sempre a mesma para "e-mail inexistente" e "senha
    errada": distinguir as duas entregaria ao atacante a lista de e-mails.
    """
    email = (email or "").strip().lower()
    usuario = db.session.scalar(db.select(Usuario).filter_by(email=email))
    generico = "E-mail ou senha inválidos."

    if usuario is None:
        check_password_hash(_HASH_FICTICIO, senha or "")  # gasta o mesmo tempo
        raise ErroAutenticacao(generico)

    agora = agora_utc()
    if usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
        minutos = int((usuario.bloqueado_ate - agora).total_seconds() // 60) + 1
        raise ErroAutenticacao(
            f"Muitas tentativas. Conta bloqueada por mais {minutos} min."
        )

    if not usuario.conferir_senha(senha or ""):
        usuario.tentativas_falhas += 1
        limite = current_app.config["LOGIN_MAX_TENTATIVAS"]
        if usuario.tentativas_falhas >= limite:
            usuario.bloqueado_ate = agora + timedelta(
                minutes=current_app.config["LOGIN_BLOQUEIO_MINUTOS"]
            )
            usuario.tentativas_falhas = 0
        db.session.commit()
        raise ErroAutenticacao(generico)

    if not usuario.ativo:
        raise ErroAutenticacao("Usuário desativado. Procure um administrador.")

    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    usuario.ultimo_login = agora
    db.session.commit()
    return usuario


def alternar_ativo(alvo: Usuario, quem_pede: Usuario) -> None:
    if alvo.id == quem_pede.id:
        raise ErroValidacao("Você não pode desativar a si mesmo.")
    alvo.ativo = not alvo.ativo
    db.session.commit()


def existe_algum_usuario() -> bool:
    return db.session.scalar(db.select(db.func.count(Usuario.id))) > 0
