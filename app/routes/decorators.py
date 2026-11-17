"""Decoradores de autorização.

Um decorador é uma função que embrulha outra: roda algo antes (aqui, a
checagem de login) e só então, se for o caso, chama a rota original.
"""
from functools import wraps

from flask import abort, flash, g, redirect, request, url_for


def login_obrigatorio(rota):
    @wraps(rota)  # preserva nome e docstring da rota original
    def envoltorio(*args, **kwargs):
        if g.get("usuario") is None:
            flash("Entre para continuar.", "aviso")
            return redirect(url_for("auth.login", next=request.full_path))
        return rota(*args, **kwargs)
    return envoltorio


def admin_obrigatorio(rota):
    @wraps(rota)
    @login_obrigatorio
    def envoltorio(*args, **kwargs):
        if not g.usuario.is_admin:
            abort(403)
        return rota(*args, **kwargs)
    return envoltorio
