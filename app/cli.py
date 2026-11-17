"""Comandos de terminal:  flask --app wsgi <comando>

    seed               apaga o banco e cria dados de demonstração
    criar-admin        cria um administrador (pergunta nome, e-mail e senha)
    verificar-estoque  confere se os saldos batem com o livro-razão
"""
import random

import click
from flask import Flask

from .extensions import db
from .models import Papel, Produto
from .services import estoque, usuarios


def registrar_comandos(app: Flask) -> None:

    @app.cli.command("seed")
    @click.option("--sim", is_flag=True, help="Não pede confirmação.")
    def seed(sim):
        """Recria o banco com usuários, produtos e movimentações de exemplo."""
        if not sim:
            click.confirm("Isto APAGA todos os dados. Continuar?", abort=True)
        db.drop_all()
        db.create_all()

        admin = usuarios.criar_usuario("Administrador Demo", "admin@demo.com", "Admin123", Papel.ADMIN)
        oper = usuarios.criar_usuario("Operador Demo", "operador@demo.com", "Operador123")

        catalogo = [
            ("CAB-HDMI-2M", "Cabo HDMI 2 m", "Informática", "un", 10, 1890),
            ("MOU-USB-01", "Mouse óptico USB", "Informática", "un", 8, 2490),
            ("TEC-ABNT2", "Teclado ABNT2", "Informática", "un", 5, 5990),
            ("PAP-A4-500", "Papel A4 (resma 500 fls)", "Escritório", "pct", 20, 2750),
            ("CAN-AZ-50", "Caneta esferográfica azul (cx 50)", "Escritório", "cx", 4, 3200),
            ("ALC-70-1L", "Álcool 70% 1 L", "Limpeza", "L", 12, 990),
            ("LUV-NIT-M", "Luva nitrílica M (par)", "EPI", "par", 30, 85),
            ("SSD-480", "SSD SATA 480 GB", "Informática", "un", 3, 18900),
        ]
        rng = random.Random(42)  # semente fixa: os dados saem iguais a cada seed
        for sku, nome, cat, un, minimo, custo in catalogo:
            p = Produto(sku=sku, nome=nome, categoria=cat, unidade=un, estoque_minimo=minimo)
            db.session.add(p)
            db.session.commit()
            estoque.registrar_entrada(p.id, minimo * 3, custo, admin, documento=f"NF {rng.randint(1000, 9999)}", motivo="Estoque inicial")
            estoque.registrar_entrada(p.id, minimo, round(custo * 1.08), admin, documento=f"NF {rng.randint(1000, 9999)}", motivo="Reposição")
            for _ in range(rng.randint(2, 5)):
                p = db.session.get(Produto, p.id)
                qtd = rng.randint(1, max(1, p.estoque // 3))
                estoque.registrar_saida(p.id, qtd, oper, motivo=rng.choice(
                    ["Requisição do setor administrativo", "Uso no laboratório", "Manutenção", "Venda balcão"]))

        # Um produto propositalmente abaixo do mínimo, para o alerta aparecer.
        ssd = db.session.scalar(db.select(Produto).filter_by(sku="SSD-480"))
        estoque.registrar_saida(ssd.id, ssd.estoque - 1, oper, motivo="Montagem de máquinas")

        click.secho("Banco populado.", fg="green")
        click.echo("  admin@demo.com    / Admin123     (administrador)")
        click.echo("  operador@demo.com / Operador123  (operador)")

    @app.cli.command("criar-admin")
    @click.option("--nome", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--senha", prompt=True, hide_input=True, confirmation_prompt=True)
    def criar_admin(nome, email, senha):
        """Cria um usuário administrador."""
        try:
            u = usuarios.criar_usuario(nome, email, senha, Papel.ADMIN)
        except ValueError as e:
            raise click.ClickException(str(e))
        click.secho(f"Administrador {u.email} criado.", fg="green")

    @app.cli.command("verificar-estoque")
    def verificar_estoque():
        """Recalcula os saldos a partir do razão e aponta divergências."""
        divergencias = estoque.verificar_integridade()
        if not divergencias:
            click.secho("Íntegro: todos os saldos batem com o livro-razão.", fg="green")
            return
        for d in divergencias:
            click.secho(
                f"{d.produto.sku}: cache={d.estoque_cache} razão={d.estoque_razao} | "
                f"valor cache={d.valor_cache} razão={d.valor_razao}", fg="red",
            )
        raise SystemExit(1)
