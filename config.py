"""Configurações por ambiente.

Cada classe é um "perfil". A fábrica de aplicação (app/__init__.py) escolhe
um deles; assim o mesmo código roda em desenvolvimento, em teste e em
produção, mudando apenas a configuração — nunca o código.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # A chave secreta assina o cookie de sessão. Quem a conhece pode forjar
    # sessões; por isso ela vem do ambiente e nunca deveria ir para o Git.
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-inseguro-troque-em-producao")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'estoque.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessão: expira em 2 h, cookie inacessível ao JavaScript (HttpOnly) e não
    # enviado em requisições vindas de outros sites (SameSite=Lax).
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    # Política de bloqueio contra força bruta no login.
    LOGIN_MAX_TENTATIVAS = 5
    LOGIN_BLOQUEIO_MINUTOS = 15

    ITENS_POR_PAGINA = 20


class DevConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # banco em memória, some ao fim
    WTF_CSRF_ENABLED = False                # testes não precisam do token


class ProdConfig(Config):
    SESSION_COOKIE_SECURE = True  # só envia o cookie por HTTPS


PERFIS = {"dev": DevConfig, "test": TestConfig, "prod": ProdConfig}
