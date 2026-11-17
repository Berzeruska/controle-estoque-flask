from app.extensions import db
from app.models import Usuario
from app.utils import destino_seguro
from tests.conftest import entrar


def test_senha_nunca_e_gravada_em_texto_puro(admin):
    assert admin.senha_hash != "Senha123"
    assert admin.senha_hash.startswith(("scrypt:", "pbkdf2:"))
    assert admin.conferir_senha("Senha123")


def test_sem_usuarios_redireciona_para_primeiro_acesso(client):
    r = client.get("/auth/login")
    assert r.status_code == 302 and "/auth/primeiro-acesso" in r.location


def test_primeiro_acesso_cria_admin_e_depois_some(client):
    r = client.post("/auth/primeiro-acesso", data={
        "nome": "Chefe", "email": "chefe@x.com", "senha": "Abc12345", "confirmacao": "Abc12345"})
    assert r.status_code == 302
    assert db.session.scalar(db.select(Usuario)).is_admin
    assert client.get("/auth/primeiro-acesso").status_code == 302  # não pode ser reusado


def test_login_correto_e_logout(client, admin):
    assert entrar(client, "ana@teste.com").status_code == 302
    assert client.get("/painel").status_code == 200
    client.post("/auth/logout")
    assert client.get("/painel").status_code == 302


def test_mensagem_igual_para_email_inexistente_e_senha_errada(client, admin):
    r1 = entrar(client, "ninguem@teste.com")
    r2 = entrar(client, "ana@teste.com", "Errada123")
    assert r1.status_code == r2.status_code == 401
    assert "E-mail ou senha inválidos." in r1.get_data(as_text=True)
    assert "E-mail ou senha inválidos." in r2.get_data(as_text=True)


def test_bloqueio_apos_cinco_tentativas(client, admin):
    for _ in range(5):
        entrar(client, "ana@teste.com", "Errada123")
    r = entrar(client, "ana@teste.com")  # agora com a senha CERTA
    assert r.status_code == 401
    assert "bloqueada" in r.get_data(as_text=True)


def test_rota_protegida_exige_login(client):
    r = client.get("/produtos/")
    assert r.status_code == 302 and "/auth/login" in r.location


def test_operador_nao_acessa_area_de_admin(client, admin, operador):
    entrar(client, "otto@teste.com")
    assert client.get("/usuarios/").status_code == 403
    assert client.get("/produtos/novo").status_code == 403


def test_usuario_desativado_perde_a_sessao(client, admin, operador):
    entrar(client, "otto@teste.com")
    operador.ativo = False
    db.session.commit()
    assert client.get("/painel").status_code == 302


def test_open_redirect_bloqueado():
    assert destino_seguro("/produtos/") == "/produtos/"
    assert destino_seguro("https://golpe.com") is None
    assert destino_seguro("//golpe.com") is None


def test_cabecalhos_de_seguranca(client):
    r = client.get("/auth/primeiro-acesso")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"


def test_post_sem_token_csrf_e_recusado(app, client, admin):
    app.config["WTF_CSRF_ENABLED"] = True
    r = client.post("/auth/login", data={"email": "ana@teste.com", "senha": "Senha123"})
    assert r.status_code == 400
