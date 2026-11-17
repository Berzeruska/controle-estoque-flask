import csv
import io
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from ..extensions import db
from ..models import Movimentacao, Produto, TipoMovimentacao
from ..services import estoque as svc
from ..utils import FUSO_LOCAL, formatar_data, para_centavos
from .decorators import admin_obrigatorio, login_obrigatorio

bp = Blueprint("movimentacoes", __name__, url_prefix="/movimentacoes")


def _consulta_filtrada(args):
    """Monta a consulta a partir dos filtros da URL (?produto=&tipo=&de=&ate=)."""
    consulta = db.select(Movimentacao).order_by(Movimentacao.id.desc())
    if (pid := args.get("produto", type=int)):
        consulta = consulta.filter_by(produto_id=pid)
    if (tipo := args.get("tipo")) in {t.value for t in TipoMovimentacao}:
        consulta = consulta.filter_by(tipo=TipoMovimentacao(tipo))

    def _data_utc(texto, fim_do_dia=False):
        """'2026-11-17' (dia em Brasília) -> datetime UTC sem fuso, como no banco."""
        try:
            d = datetime.strptime(texto, "%Y-%m-%d").replace(tzinfo=FUSO_LOCAL)
        except (TypeError, ValueError):
            return None
        if fim_do_dia:
            d += timedelta(days=1)
        return d.astimezone(timezone.utc).replace(tzinfo=None)

    if (de := _data_utc(args.get("de"))):
        consulta = consulta.where(Movimentacao.criado_em >= de)
    if (ate := _data_utc(args.get("ate"), fim_do_dia=True)):
        consulta = consulta.where(Movimentacao.criado_em < ate)
    return consulta


@bp.route("/")
@login_obrigatorio
def lista():
    pagina = db.paginate(
        _consulta_filtrada(request.args),
        per_page=20, error_out=False,
    )
    produtos = db.session.scalars(db.select(Produto).order_by(Produto.nome)).all()
    filtros = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("movimentacoes/lista.html", pagina=pagina, produtos=produtos, filtros=filtros)


@bp.route("/nova", methods=["GET", "POST"])
@login_obrigatorio
def nova():
    produtos = db.session.scalars(
        db.select(Produto).filter_by(ativo=True).order_by(Produto.nome)
    ).all()
    f = request.form if request.method == "POST" else request.args

    if request.method == "POST":
        try:
            pid = int(f.get("produto") or 0)
            quantidade = int(f.get("quantidade") or 0)
            tipo = TipoMovimentacao(f.get("tipo"))
            if tipo == TipoMovimentacao.ENTRADA:
                mov = svc.registrar_entrada(
                    pid, quantidade, para_centavos(f.get("custo_unitario")), g.usuario,
                    motivo=f.get("motivo"), documento=f.get("documento"),
                )
            else:
                mov = svc.registrar_saida(
                    pid, quantidade, g.usuario, motivo=f.get("motivo"), documento=f.get("documento"),
                )
        except (ValueError, svc.ErroEstoque) as e:
            flash(str(e), "erro")
            return render_template("movimentacoes/form.html", produtos=produtos, form=f), 400

        verbo = "Entrada" if mov.tipo == TipoMovimentacao.ENTRADA else "Saída"
        flash(
            f"{verbo} de {mov.quantidade} {mov.produto.unidade} de {mov.produto.nome} registrada. "
            f"Saldo: {mov.saldo_apos}.", "sucesso",
        )
        if mov.produto.situacao != "ok":
            flash(f"Atenção: {mov.produto.nome} está abaixo do estoque mínimo.", "aviso")
        return redirect(url_for("produtos.detalhe", pid=mov.produto_id))

    return render_template("movimentacoes/form.html", produtos=produtos, form=f)


@bp.post("/<int:mid>/estornar")
@admin_obrigatorio
def estornar(mid):
    try:
        est = svc.estornar(mid, g.usuario, request.form.get("motivo", ""))
    except svc.ErroEstoque as e:
        flash(str(e), "erro")
        mov = db.session.get(Movimentacao, mid)
        return redirect(url_for("produtos.detalhe", pid=mov.produto_id) if mov else url_for("movimentacoes.lista"))
    flash(f"Movimentação #{mid} estornada (lançamento #{est.id}).", "sucesso")
    return redirect(url_for("produtos.detalhe", pid=est.produto_id))


@bp.route("/exportar.csv")
@login_obrigatorio
def exportar():
    """CSV com ';' e BOM UTF-8: o Excel em português abre direto, com acentos."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(["id", "data", "tipo", "sku", "produto", "quantidade",
                       "valor_total", "saldo_apos", "usuario", "documento", "motivo", "estorno_de"])
    for m in db.session.scalars(_consulta_filtrada(request.args)):
        escritor.writerow([
            m.id, formatar_data(m.criado_em), m.tipo.value, m.produto.sku, m.produto.nome,
            m.quantidade, f"{m.valor_total_centavos / 100:.2f}".replace(".", ","),
            m.saldo_apos, m.usuario.email, m.documento or "", m.motivo or "", m.estorno_de_id or "",
        ])
    return Response(
        "﻿" + buffer.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=movimentacoes.csv"},
    )
