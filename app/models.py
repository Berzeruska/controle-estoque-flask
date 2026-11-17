"""Modelos (tabelas) do sistema.

Três entidades:
    Usuario       — quem acessa o sistema
    Produto       — o que é estocado; guarda o saldo atual em cache
    Movimentacao  — o livro-razão: cada entrada ou saída é uma linha imutável

Princípio central: o saldo de um produto é a SOMA de suas movimentações.
O campo `Produto.estoque` é apenas um cache desse somatório, atualizado na
mesma transação que grava a movimentação. O comando `flask verificar-estoque`
recalcula tudo a partir do razão e acusa qualquer divergência.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def agora_utc() -> datetime:
    """Data/hora em UTC, sem fuso (o SQLite não guarda fuso).

    Gravar sempre em UTC e converter só na exibição evita a confusão do
    horário de verão e de servidores em fusos diferentes.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Papel(str, enum.Enum):
    ADMIN = "admin"        # gerencia usuários, produtos e pode estornar
    OPERADOR = "operador"  # registra entradas e saídas


class TipoMovimentacao(str, enum.Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # Nunca a senha: apenas o hash (scrypt, com sal aleatório embutido).
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[Papel] = mapped_column(default=Papel.OPERADOR)
    ativo: Mapped[bool] = mapped_column(default=True)

    tentativas_falhas: Mapped[int] = mapped_column(default=0)
    bloqueado_ate: Mapped[datetime | None]
    ultimo_login: Mapped[datetime | None]
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)

    movimentacoes: Mapped[list[Movimentacao]] = relationship(back_populates="usuario")

    def definir_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_admin(self) -> bool:
        return self.papel == Papel.ADMIN

    def __repr__(self) -> str:
        return f"<Usuario {self.email}>"


class Produto(db.Model):
    __tablename__ = "produtos"
    __table_args__ = (
        # Defesa em profundidade: mesmo que o código falhe, o próprio banco
        # recusa saldo negativo.
        CheckConstraint("estoque >= 0", name="ck_estoque_nao_negativo"),
        CheckConstraint("valor_estoque_centavos >= 0", name="ck_valor_nao_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str] = mapped_column(String(60), default="Geral")
    unidade: Mapped[str] = mapped_column(String(10), default="un")
    estoque_minimo: Mapped[int] = mapped_column(default=0)
    ativo: Mapped[bool] = mapped_column(default=True)

    # Cache do razão. Dinheiro em CENTAVOS INTEIROS: float não representa
    # 0,10 com exatidão (0.1 + 0.2 == 0.30000000000000004).
    estoque: Mapped[int] = mapped_column(default=0)
    valor_estoque_centavos: Mapped[int] = mapped_column(default=0)

    # Controle de concorrência otimista: a cada UPDATE o SQLAlchemy faz
    # "... WHERE id = ? AND versao = ?" e incrementa a versão. Se outra
    # requisição alterou o produto no meio do caminho, nenhuma linha casa e
    # ele lança StaleDataError — em vez de sobrescrever o saldo em silêncio.
    versao: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": versao}  # noqa: RUF012

    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)

    movimentacoes: Mapped[list[Movimentacao]] = relationship(
        back_populates="produto", order_by="Movimentacao.id.desc()"
    )

    @property
    def custo_medio_centavos(self) -> int:
        """Custo médio ponderado: valor total do estoque ÷ quantidade."""
        if self.estoque == 0:
            return 0
        return round(self.valor_estoque_centavos / self.estoque)

    @property
    def situacao(self) -> str:
        if self.estoque == 0:
            return "zerado"
        if self.estoque <= self.estoque_minimo:
            return "baixo"
        return "ok"

    def __repr__(self) -> str:
        return f"<Produto {self.sku}>"


class Movimentacao(db.Model):
    """Linha do livro-razão. Nunca é editada nem apagada.

    Um lançamento errado se corrige com um ESTORNO: uma nova movimentação de
    sentido oposto que aponta para a original. É o mesmo princípio da
    contabilidade de partidas dobradas e dos logs de bancos de dados: a
    história não se reescreve, acrescenta-se.
    """
    __tablename__ = "movimentacoes"
    __table_args__ = (CheckConstraint("quantidade > 0", name="ck_quantidade_positiva"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[TipoMovimentacao]
    quantidade: Mapped[int]
    valor_total_centavos: Mapped[int]
    saldo_apos: Mapped[int]  # fotografia do saldo logo após o lançamento
    motivo: Mapped[str | None] = mapped_column(Text)
    documento: Mapped[str | None] = mapped_column(String(60))  # nota fiscal, pedido…

    # unique=True: uma movimentação só pode ser estornada uma vez.
    estorno_de_id: Mapped[int | None] = mapped_column(
        ForeignKey("movimentacoes.id"), unique=True
    )
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc, index=True)

    produto: Mapped[Produto] = relationship(back_populates="movimentacoes")
    usuario: Mapped[Usuario] = relationship(back_populates="movimentacoes")
    estorno_de: Mapped[Movimentacao | None] = relationship(
        remote_side=[id], back_populates="estornada_por"
    )
    estornada_por: Mapped[Movimentacao | None] = relationship(back_populates="estorno_de")

    @property
    def custo_unitario_centavos(self) -> int:
        return round(self.valor_total_centavos / self.quantidade)

    @property
    def sinal(self) -> int:
        return 1 if self.tipo == TipoMovimentacao.ENTRADA else -1
