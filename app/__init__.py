"""Fábrica da aplicação (application factory).

Em vez de um `app = Flask(...)` global, uma função monta a aplicação sob
demanda. Vantagens: os testes criam uma instância limpa com configuração de
teste; não há estado global escondido; extensões e blueprints são
registrados num só lugar.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, g, render_template, session

from config import PERFIS

from . import utils
from .extensions import csrf, db


def create_app(perfil: str = "dev") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(PERFIS[perfil])
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    if perfil == "prod" and app.config["SECRET_KEY"].startswith("dev-"):
        raise RuntimeError("Defina a variável de ambiente SECRET_KEY em produção.")

    db.init_app(app)
    csrf.init_app(app)

    from .routes import registrar_blueprints
    registrar_blueprints(app)

    _registrar_filtros(app)
    _registrar_hooks(app)
    _registrar_erros(app)

    from .cli import registrar_comandos
    registrar_comandos(app)

    with app.app_context():
        from . import models  # noqa: F401  (registra as tabelas no metadata)
        db.create_all()

    return app


def _registrar_filtros(app: Flask) -> None:
    app.jinja_env.filters["brl"] = utils.formatar_brl
    app.jinja_env.filters["data"] = utils.formatar_data
    app.jinja_env.filters["reais_input"] = utils.formatar_reais_input


def _registrar_hooks(app: Flask) -> None:
    from .models import Usuario

    @app.before_request
    def carregar_usuario():
        """Disponibiliza o usuário logado em `g.usuario` para rotas e templates."""
        g.usuario = None
        uid = session.get("uid")
        if uid is not None:
            usuario = db.session.get(Usuario, uid)
            if usuario is None or not usuario.ativo:
                session.clear()   # usuário apagado/desativado: derruba a sessão
            else:
                g.usuario = usuario

    @app.context_processor
    def injetar_usuario():
        return {"usuario_atual": g.get("usuario")}

    @app.after_request
    def cabecalhos_de_seguranca(resp):
        # Content-Security-Policy: o navegador só executa recursos do próprio
        # domínio — um script injetado (XSS) não roda.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")          # anti-clickjacking
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp


def _registrar_erros(app: Flask) -> None:
    @app.errorhandler(403)
    def proibido(_e):
        return render_template("erro.html", codigo=403, mensagem="Acesso restrito a administradores."), 403

    @app.errorhandler(404)
    def nao_encontrado(_e):
        return render_template("erro.html", codigo=404, mensagem="Página não encontrada."), 404

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_invalido(_e):
        return render_template(
            "erro.html", codigo=400,
            mensagem="Formulário expirado ou inválido. Volte, recarregue a página e tente de novo.",
        ), 400
