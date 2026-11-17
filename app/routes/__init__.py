from flask import Flask


def registrar_blueprints(app: Flask) -> None:
    from .auth import bp as auth_bp
    from .movimentacoes import bp as mov_bp
    from .painel import bp as painel_bp
    from .produtos import bp as produtos_bp
    from .usuarios import bp as usuarios_bp

    for bp in (auth_bp, painel_bp, produtos_bp, mov_bp, usuarios_bp):
        app.register_blueprint(bp)
