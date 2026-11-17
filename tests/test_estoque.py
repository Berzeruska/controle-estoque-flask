import pytest

from app.extensions import db
from app.models import Produto
from app.services import estoque
from app.utils import formatar_brl, para_centavos
from tests.conftest import entrar


def test_entrada_aumenta_saldo_e_valor(produto, admin):
    estoque.registrar_entrada(produto.id, 10, 250, admin)  # 10 un a R$ 2,50
    assert produto.estoque == 10
    assert produto.valor_estoque_centavos == 2500


def test_custo_medio_ponderado(produto, admin):
    estoque.registrar_entrada(produto.id, 10, 1000, admin)  # 10 × R$ 10
    estoque.registrar_entrada(produto.id, 10, 2000, admin)  # 10 × R$ 20
    assert produto.custo_medio_centavos == 1500              # média: R$ 15
    saida = estoque.registrar_saida(produto.id, 4, admin)
    assert saida.valor_total_centavos == 6000                # 4 × R$ 15


def test_saida_total_zera_valor_sem_centavo_orfao(produto, admin):
    estoque.registrar_entrada(produto.id, 3, 333, admin)
    estoque.registrar_entrada(produto.id, 7, 101, admin)
    estoque.registrar_saida(produto.id, 1, admin)
    estoque.registrar_saida(produto.id, 9, admin)
    assert produto.estoque == 0 and produto.valor_estoque_centavos == 0


def test_saida_maior_que_saldo_e_recusada(produto, admin):
    estoque.registrar_entrada(produto.id, 2, 100, admin)
    with pytest.raises(estoque.EstoqueInsuficiente):
        estoque.registrar_saida(produto.id, 3, admin)
    assert produto.estoque == 2  # nada mudou


@pytest.mark.parametrize("qtd", [0, -5])
def test_quantidade_invalida(produto, admin, qtd):
    with pytest.raises(estoque.ErroEstoque):
        estoque.registrar_entrada(produto.id, qtd, 100, admin)


def test_estorno_de_entrada(produto, admin):
    e = estoque.registrar_entrada(produto.id, 5, 100, admin)
    est = estoque.estornar(e.id, admin, "lançado no produto errado")
    assert produto.estoque == 0 and est.estorno_de_id == e.id
    with pytest.raises(estoque.ErroEstoque, match="já foi estornada"):
        estoque.estornar(e.id, admin, "de novo")
    with pytest.raises(estoque.ErroEstoque, match="Não se estorna um estorno"):
        estoque.estornar(est.id, admin, "estorno do estorno")


def test_estorno_de_saida_devolve_pelo_mesmo_valor(produto, admin):
    estoque.registrar_entrada(produto.id, 10, 1000, admin)
    s = estoque.registrar_saida(produto.id, 4, admin)
    estoque.estornar(s.id, admin, "devolução")
    assert produto.estoque == 10 and produto.valor_estoque_centavos == 10000


def test_integridade_detecta_adulteracao(produto, admin):
    estoque.registrar_entrada(produto.id, 5, 100, admin)
    assert estoque.verificar_integridade() == []
    db.session.execute(db.text("UPDATE produtos SET estoque = 999 WHERE id = :id"), {"id": produto.id})
    db.session.commit()
    divergencias = estoque.verificar_integridade()
    assert len(divergencias) == 1 and divergencias[0].estoque_razao == 5


def test_banco_recusa_saldo_negativo(produto):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.execute(db.text("UPDATE produtos SET estoque = -1 WHERE id = :id"), {"id": produto.id})
    db.session.rollback()


def test_concorrencia_otimista_detecta_atualizacao_perdida(app, produto):
    """Duas "requisições" leem o mesmo produto; a segunda a gravar deve falhar."""
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.exc import StaleDataError

    with Session(db.engine) as s1, Session(db.engine) as s2:
        p1 = s1.get(Produto, produto.id)
        p2 = s2.get(Produto, produto.id)
        p1.estoque += 10
        s1.commit()                 # versão 1 -> 2
        p2.estoque += 5             # p2 ainda acha que está na versão 1
        with pytest.raises(StaleDataError):
            s2.commit()


def test_dinheiro_em_centavos():
    assert para_centavos("1.234,56") == 123456
    assert para_centavos("0,1") == 10
    assert para_centavos("19.90") == 1990
    assert formatar_brl(123456) == "R$ 1.234,56"
    with pytest.raises(ValueError):
        para_centavos("abc")


def test_fluxo_http_entrada_e_saida(client, admin, produto):
    entrar(client, "ana@teste.com")
    r = client.post("/movimentacoes/nova", data={
        "tipo": "entrada", "produto": produto.id, "quantidade": 8, "custo_unitario": "12,50"})
    assert r.status_code == 302
    r = client.post("/movimentacoes/nova", data={"tipo": "saida", "produto": produto.id, "quantidade": 20})
    assert r.status_code == 400 and "Estoque insuficiente" in r.get_data(as_text=True)
    db.session.refresh(produto)
    assert produto.estoque == 8 and produto.valor_estoque_centavos == 10000


def test_exportacao_csv(client, admin, produto):
    estoque.registrar_entrada(produto.id, 1, 100, admin)
    entrar(client, "ana@teste.com")
    r = client.get("/movimentacoes/exportar.csv")
    texto = r.get_data(as_text=True)
    assert r.mimetype == "text/csv" and texto.startswith("﻿id;data;tipo")
    assert "TST-1" in texto
