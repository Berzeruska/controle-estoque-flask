from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..models import Papel
from ..services import usuarios as svc
from ..utils import destino_seguro

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not svc.existe_algum_usuario():
        return redirect(url_for("auth.primeiro_acesso"))
    if g.usuario:
        return redirect(url_for("painel.inicio"))

    if request.method == "POST":
        try:
            usuario = svc.autenticar(request.form.get("email"), request.form.get("senha"))
        except svc.ErroAutenticacao as e:
            flash(str(e), "erro")
            return render_template("auth/login.html", email=request.form.get("email", "")), 401

        # Limpa a sessão antiga antes de gravar a nova (evita fixação de sessão).
        session.clear()
        session.permanent = True
        session["uid"] = usuario.id
        flash(f"Bem-vindo, {usuario.nome.split()[0]}.", "sucesso")
        return redirect(destino_seguro(request.args.get("next")) or url_for("painel.inicio"))

    return render_template("auth/login.html", email="")


@bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    """Só existe enquanto o banco não tem usuários: cria o primeiro administrador."""
    if svc.existe_algum_usuario():
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        f = request.form
        if f.get("senha") != f.get("confirmacao"):
            flash("As senhas não coincidem.", "erro")
        else:
            try:
                usuario = svc.criar_usuario(f.get("nome"), f.get("email"), f.get("senha"), Papel.ADMIN)
            except svc.ErroValidacao as e:
                flash(str(e), "erro")
            else:
                session.clear()
                session["uid"] = usuario.id
                flash("Administrador criado. Cadastre seu primeiro produto.", "sucesso")
                return redirect(url_for("produtos.novo"))
        return render_template("auth/primeiro_acesso.html", form=f), 400

    return render_template("auth/primeiro_acesso.html", form={})


@bp.post("/logout")  # POST, não GET: um <img src="/auth/logout"> não desloga ninguém
def logout():
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))
