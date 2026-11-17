"""Regras de estoque: entrada, saída, estorno e auditoria do razão.

Toda alteração de saldo passa por `_lancar`, que faz numa ÚNICA transação:
    1. lê o produto (com sua versão);
    2. calcula o novo saldo e o novo valor;
    3. grava a movimentação e o produto;
    4. confirma (commit).
Se outra requisição alterou o mesmo produto entre o passo 1 e o 4, o
SQLAlchemy detecta pela coluna `versao` e lança StaleDataError; nesse caso
desfazemos tudo e tentamos de novo, com o saldo fresco.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from ..extensions import db
from ..models import Movimentacao, Produto, TipoMovimentacao, Usuario

MAX_TENTATIVAS = 3


class ErroEstoque(ValueError):
    pass


class EstoqueInsuficiente(ErroEstoque):
    pass


class ConflitoConcorrencia(ErroEstoque):
    pass


def custo_saida(valor_estoque: int, estoque: int, quantidade: int) -> int:
    """Valor (em centavos) que sai do estoque ao retirar `quantidade` unidades.

    Saída pelo custo médio ponderado, arredondado meio-para-cima, só com
    inteiros. Quando sai TUDO (quantidade == estoque), o resultado é
    exatamente o valor total — o estoque zera sem deixar centavo órfão.
    """
    return (2 * valor_estoque * quantidade + estoque) // (2 * estoque)


def _lancar(
    produto_id: int,
    tipo: TipoMovimentacao,
    quantidade: int,
    usuario: Usuario,
    *,
    custo_unitario_centavos: int | None = None,
    valor_total_centavos: int | None = None,
    motivo: str | None = None,
    documento: str | None = None,
    estorno_de: Movimentacao | None = None,
) -> Movimentacao:
    if not isinstance(quantidade, int) or quantidade <= 0:
        raise ErroEstoque("A quantidade deve ser um inteiro maior que zero.")

    for _ in range(MAX_TENTATIVAS):
        produto = db.session.get(Produto, produto_id, populate_existing=True)
        if produto is None:
            raise ErroEstoque("Produto não encontrado.")
        if not produto.ativo and estorno_de is None:
            raise ErroEstoque("Produto inativo não recebe movimentações.")

        if tipo == TipoMovimentacao.ENTRADA:
            if valor_total_centavos is not None:
                valor_mov = valor_total_centavos
            elif custo_unitario_centavos is not None and custo_unitario_centavos >= 0:
                valor_mov = custo_unitario_centavos * quantidade
            else:
                raise ErroEstoque("Informe o custo unitário da entrada.")
            produto.estoque += quantidade
            produto.valor_estoque_centavos += valor_mov
        else:
            if produto.estoque < quantidade:
                raise EstoqueInsuficiente(
                    f"Estoque insuficiente: há {produto.estoque} {produto.unidade}, "
                    f"pediu-se {quantidade}."
                )
            valor_mov = custo_saida(produto.valor_estoque_centavos, produto.estoque, quantidade)
            produto.estoque -= quantidade
            produto.valor_estoque_centavos -= valor_mov

        mov = Movimentacao(
            produto=produto,
            usuario=usuario,
            tipo=tipo,
            quantidade=quantidade,
            valor_total_centavos=valor_mov,
            saldo_apos=produto.estoque,
            motivo=(motivo or "").strip() or None,
            documento=(documento or "").strip() or None,
            estorno_de=estorno_de,
        )
        db.session.add(mov)
        try:
            db.session.commit()
            return mov
        except StaleDataError:
            db.session.rollback()       # alguém mexeu antes: recomeça com saldo fresco
            continue
        except IntegrityError as e:
            db.session.rollback()
            raise ErroEstoque("Operação recusada pelo banco de dados.") from e

    raise ConflitoConcorrencia("O produto foi alterado por outra pessoa. Tente de novo.")


def registrar_entrada(produto_id, quantidade, custo_unitario_centavos, usuario, motivo=None, documento=None):
    return _lancar(
        produto_id, TipoMovimentacao.ENTRADA, quantidade, usuario,
        custo_unitario_centavos=custo_unitario_centavos, motivo=motivo, documento=documento,
    )


def registrar_saida(produto_id, quantidade, usuario, motivo=None, documento=None):
    return _lancar(
        produto_id, TipoMovimentacao.SAIDA, quantidade, usuario,
        motivo=motivo, documento=documento,
    )


def estornar(mov_id: int, usuario: Usuario, motivo: str) -> Movimentacao:
    """Anula uma movimentação lançando outra, de sentido contrário."""
    original = db.session.get(Movimentacao, mov_id)
    if original is None:
        raise ErroEstoque("Movimentação não encontrada.")
    if original.estorno_de_id is not None:
        raise ErroEstoque("Não se estorna um estorno; lance uma nova movimentação.")
    if original.estornada_por is not None:
        raise ErroEstoque("Esta movimentação já foi estornada.")
    if not (motivo or "").strip():
        raise ErroEstoque("Informe o motivo do estorno.")

    if original.tipo == TipoMovimentacao.ENTRADA:
        # Desfaz uma entrada: retira a mesma quantidade (pelo custo médio).
        return _lancar(
            original.produto_id, TipoMovimentacao.SAIDA, original.quantidade, usuario,
            motivo=f"Estorno: {motivo}", estorno_de=original,
        )
    # Desfaz uma saída: devolve a quantidade pelo MESMO valor que saiu.
    return _lancar(
        original.produto_id, TipoMovimentacao.ENTRADA, original.quantidade, usuario,
        valor_total_centavos=original.valor_total_centavos,
        motivo=f"Estorno: {motivo}", estorno_de=original,
    )


@dataclass
class Divergencia:
    produto: Produto
    estoque_cache: int
    estoque_razao: int
    valor_cache: int
    valor_razao: int


def verificar_integridade() -> list[Divergencia]:
    """Recalcula cada saldo somando o razão e compara com o cache do produto."""
    sinal = db.case((Movimentacao.tipo == TipoMovimentacao.ENTRADA, 1), else_=-1)
    linhas = db.session.execute(
        db.select(
            Movimentacao.produto_id,
            db.func.sum(sinal * Movimentacao.quantidade),
            db.func.sum(sinal * Movimentacao.valor_total_centavos),
        ).group_by(Movimentacao.produto_id)
    ).all()
    somas = {pid: (q or 0, v or 0) for pid, q, v in linhas}

    divergencias = []
    for produto in db.session.scalars(db.select(Produto)):
        q, v = somas.get(produto.id, (0, 0))
        if q != produto.estoque or v != produto.valor_estoque_centavos:
            divergencias.append(
                Divergencia(produto, produto.estoque, q, produto.valor_estoque_centavos, v)
            )
    return divergencias
