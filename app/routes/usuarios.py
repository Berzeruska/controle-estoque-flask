from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Papel, Usuario
from ..services import usuarios as svc
from .decorators import admin_obrigatorio, login_obrigatorio

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


@bp.route("/")
@admin_obrigatorio
def lista():
    usuarios = db.session.scalars(db.select(Usuario).order_by(Usuario.nome)).all()
    return render_template("usuarios/lista.html", usuarios=usuarios)


@bp.route("/novo", methods=["GET", "POST"])
@admin_obrigatorio
def novo():
    if request.method == "POST":
        f = request.form
        try:
            papel = Papel(f.get("papel", "operador"))
            u = svc.criar_usuario(f.get("nome"), f.get("email"), f.get("senha"), papel)
        except ValueError as e:
            flash(str(e), "erro")
            return render_template("usuarios/form.html", form=f), 400
        flash(f"Usuário {u.email} criado.", "sucesso")
        return redirect(url_for("usuarios.lista"))
    return render_template("usuarios/form.html", form={})


@bp.post("/<int:uid>/ativo")
@admin_obrigatorio
def alternar_ativo(uid):
    alvo = db.get_or_404(Usuario, uid)
    try:
        svc.alternar_ativo(alvo, g.usuario)
        flash(f"{alvo.nome} " + ("reativado." if alvo.ativo else "desativado."), "sucesso")
    except svc.ErroValidacao as e:
        flash(str(e), "erro")
    return redirect(url_for("usuarios.lista"))


@bp.route("/minha-senha", methods=["GET", "POST"])
@login_obrigatorio
def minha_senha():
    if request.method == "POST":
        f = request.form
        if not g.usuario.conferir_senha(f.get("atual", "")):
            flash("Senha atual incorreta.", "erro")
        elif f.get("nova") != f.get("confirmacao"):
            flash("A confirmação não coincide com a nova senha.", "erro")
        else:
            try:
                svc.validar_senha(f.get("nova", ""))
            except svc.ErroValidacao as e:
                flash(str(e), "erro")
            else:
                g.usuario.definir_senha(f["nova"])
                db.session.commit()
                flash("Senha alterada.", "sucesso")
                return redirect(url_for("painel.inicio"))
        return render_template("usuarios/minha_senha.html"), 400
    return render_template("usuarios/minha_senha.html")
