"""Funções auxiliares: dinheiro, datas e redirecionamento seguro."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")


def para_centavos(texto: str | None) -> int:
    """Converte '1.234,56' ou '1234.56' em 123456 (centavos).

    Usa Decimal, não float, para não perder precisão no caminho.
    """
    if texto is None or not str(texto).strip():
        raise ValueError("Informe um valor.")
    t = str(texto).strip().replace("R$", "").replace(" ", "")
    if "," in t:                       # formato brasileiro: 1.234,56
        t = t.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"Valor inválido: {texto!r}") from None
    if valor < 0:
        raise ValueError("O valor não pode ser negativo.")
    return int((valor * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def formatar_brl(centavos: int | None) -> str:
    """123456 -> 'R$ 1.234,56'."""
    centavos = centavos or 0
    sinal = "-" if centavos < 0 else ""
    reais, cent = divmod(abs(centavos), 100)
    reais_fmt = f"{reais:,}".replace(",", ".")
    return f"{sinal}R$ {reais_fmt},{cent:02d}"


def formatar_reais_input(centavos: int | None) -> str:
    """123456 -> '1234,56' (para preencher campos de formulário)."""
    centavos = centavos or 0
    return f"{centavos // 100},{centavos % 100:02d}"


def para_local(dt: datetime | None) -> datetime | None:
    """UTC (como gravado no banco) -> horário de Brasília."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(FUSO_LOCAL)


def formatar_data(dt: datetime | None, com_hora: bool = True) -> str:
    local = para_local(dt)
    if local is None:
        return "—"
    return local.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def destino_seguro(alvo: str | None) -> str | None:
    """Aceita só caminhos internos ('/produtos'), nunca 'https://site-malicioso'.

    Sem isso, um link como /auth/login?next=https://golpe.com faria o próprio
    sistema redirecionar o usuário para fora após o login (open redirect).
    """
    if not alvo:
        return None
    partes = urlparse(alvo)
    if partes.scheme or partes.netloc or not alvo.startswith("/") or alvo.startswith("//"):
        return None
    return alvo
