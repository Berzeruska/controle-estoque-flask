from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Produto
from .decorators import admin_obrigatorio, login_obrigatorio

bp = Blueprint("produtos", __name__, url_prefix="/produtos")

UNIDADES = ["un", "cx", "kg", "g", "L", "mL", "m", "pct", "par"]


@bp.route("/")
@login_obrigatorio
def lista():
    busca = request.args.get("q", "").strip()
    situacao = request.args.get("situacao", "")
    mostrar_inativos = request.args.get("inativos") == "1"

    consulta = db.select(Produto).order_by(Produto.nome)
    if not mostrar_inativos:
        consulta = consulta.filter_by(ativo=True)
    if busca:
        termo = f"%{busca}%"
        # Parâmetros ligados (bind params): o termo vira DADO, nunca código
        # SQL — é isso que impede injeção de SQL.
        consulta = consulta.where(
            Produto.nome.ilike(termo) | Produto.sku.ilike(termo) | Produto.categoria.ilike(termo)
        )
    produtos = db.session.scalars(consulta).all()
    if situacao in {"ok", "baixo", "zerado"}:
        produtos = [p for p in produtos if p.situacao == situacao]

    return render_template(
        "produtos/lista.html", produtos=produtos, busca=busca,
        situacao=situacao, mostrar_inativos=mostrar_inativos,
    )


@bp.route("/<int:pid>")
@login_obrigatorio
def detalhe(pid):
    produto = db.get_or_404(Produto, pid)
    return render_template("produtos/detalhe.html", produto=produto, movs=produto.movimentacoes[:50])


def _preencher(produto: Produto, form) -> None:
    sku = (form.get("sku") or "").strip().upper()
    nome = (form.get("nome") or "").strip()
    if not sku or not nome:
        raise ValueError("SKU e nome são obrigatórios.")
    try:
        minimo = int(form.get("estoque_minimo") or 0)
    except ValueError:
        raise ValueError("Estoque mínimo deve ser um número inteiro.") from None
    if minimo < 0:
        raise ValueError("Estoque mínimo não pode ser negativo.")
    unidade = form.get("unidade") or "un"
    if unidade not in UNIDADES:
        raise ValueError("Unidade inválida.")

    produto.sku = sku
    produto.nome = nome
    produto.categoria = (form.get("categoria") or "Geral").strip() or "Geral"
    produto.unidade = unidade
    produto.estoque_minimo = minimo


@bp.route("/novo", methods=["GET", "POST"])
@admin_obrigatorio
def novo():
    if request.method == "POST":
        produto = Produto()
        try:
            _preencher(produto, request.form)
            db.session.add(produto)
            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "erro")
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um produto com esse SKU.", "erro")
        else:
            flash(f"Produto {produto.sku} cadastrado. Registre a primeira entrada.", "sucesso")
            return redirect(url_for("movimentacoes.nova", produto=produto.id, tipo="entrada"))
        return render_template("produtos/form.html", produto=None, form=request.form, unidades=UNIDADES), 400
    return render_template("produtos/form.html", produto=None, form={}, unidades=UNIDADES)


@bp.route("/<int:pid>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar(pid):
    produto = db.get_or_404(Produto, pid)
    if request.method == "POST":
        try:
            _preencher(produto, request.form)
            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "erro")
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um produto com esse SKU.", "erro")
        else:
            flash("Produto atualizado.", "sucesso")
            return redirect(url_for("produtos.detalhe", pid=pid))
        return render_template("produtos/form.html", produto=produto, form=request.form, unidades=UNIDADES), 400

    form = {
        "sku": produto.sku, "nome": produto.nome, "categoria": produto.categoria,
        "unidade": produto.unidade, "estoque_minimo": produto.estoque_minimo,
    }
    return render_template("produtos/form.html", produto=produto, form=form, unidades=UNIDADES)


@bp.post("/<int:pid>/ativo")
@admin_obrigatorio
def alternar_ativo(pid):
    """Desativa em vez de apagar: o histórico de movimentações precisa do produto."""
    produto = db.get_or_404(Produto, pid)
    if produto.ativo and produto.estoque > 0:
        flash("Zere o estoque (com uma saída) antes de desativar o produto.", "erro")
    else:
        produto.ativo = not produto.ativo
        db.session.commit()
        flash("Produto " + ("reativado." if produto.ativo else "desativado."), "sucesso")
    return redirect(url_for("produtos.detalhe", pid=pid))
