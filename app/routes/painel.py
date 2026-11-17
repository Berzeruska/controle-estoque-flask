from datetime import timedelta

from flask import Blueprint, g, redirect, render_template, url_for

from ..extensions import db
from ..models import Movimentacao, Produto, TipoMovimentacao, agora_utc
from .decorators import login_obrigatorio

bp = Blueprint("painel", __name__)


@bp.route("/")
def raiz():
    return redirect(url_for("painel.inicio" if g.usuario else "auth.login"))


@bp.route("/painel")
@login_obrigatorio
def inicio():
    ativos = db.select(Produto).filter_by(ativo=True)
    produtos = db.session.scalars(ativos).all()

    totais = {
        "produtos": len(produtos),
        "unidades": sum(p.estoque for p in produtos),
        "valor": sum(p.valor_estoque_centavos for p in produtos),
        "alertas": sum(1 for p in produtos if p.situacao != "ok"),
    }
    alertas = sorted(
        (p for p in produtos if p.situacao != "ok"),
        key=lambda p: (p.estoque - p.estoque_minimo, p.nome),
    )[:8]

    ultimas = db.session.scalars(
        db.select(Movimentacao).order_by(Movimentacao.id.desc()).limit(8)
    ).all()

    # Fluxo dos últimos 7 dias, para o gráfico de barras em CSS.
    desde = agora_utc() - timedelta(days=7)
    fluxo = {
        t.value: db.session.scalar(
            db.select(db.func.coalesce(db.func.sum(Movimentacao.quantidade), 0))
            .where(Movimentacao.tipo == t, Movimentacao.criado_em >= desde)
        )
        for t in TipoMovimentacao
    }
    maior = max(fluxo.values()) or 1

    return render_template(
        "painel.html", totais=totais, alertas=alertas, ultimas=ultimas,
        fluxo=fluxo, maior=maior,
    )
