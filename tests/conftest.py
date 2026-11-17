import pytest

from app import create_app
from app.extensions import db
from app.models import Papel, Produto
from app.services import usuarios


@pytest.fixture
def app():
    app = create_app("test")
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(app):
    return usuarios.criar_usuario("Ana Admin", "ana@teste.com", "Senha123", Papel.ADMIN)


@pytest.fixture
def operador(app):
    return usuarios.criar_usuario("Otto Operador", "otto@teste.com", "Senha123")


@pytest.fixture
def produto(app):
    p = Produto(sku="TST-1", nome="Produto de teste", estoque_minimo=2)
    db.session.add(p)
    db.session.commit()
    return p


def entrar(client, email, senha="Senha123"):
    return client.post("/auth/login", data={"email": email, "senha": senha})
