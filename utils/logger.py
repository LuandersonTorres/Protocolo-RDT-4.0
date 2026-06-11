# -*- coding: utf-8 -*-
"""
utils/logger.py — Sistema de log do Simulador B (RDT 4.0).

Responsabilidades:
  - Formatar mensagens no padrão normativo: [HH:MM:SS.mmm] [B] [EVENTO] DETALHES
  - Exibir cada entrada no terminal (stdout).
  - Acrescentar (append) cada entrada ao arquivo rdt_log_B.txt.

Uso:
    from utils.logger import log
    log("FW", "SEQ=0 | ACAO=NORMAL -> encaminhado para C")
    log("ER", "datagrama malformado descartado")
"""

import sys
from datetime import datetime

# ── Configuração ──────────────────────────────────────────────────────────────
_DEVICE: str = "B"
_LOG_FILE: str = "rdt_log_B.txt"


# ── API pública ───────────────────────────────────────────────────────────────

def log(event: str, details: str) -> None:
    """Emite uma linha de log para o terminal e para rdt_log_B.txt.

    Args:
        event:   Código do evento (ex.: "FW", "ER").  Será convertido para
                 maiúsculas automaticamente.
        details: Texto livre com as informações do evento.
    """
    line = _format(event.upper(), details)
    _print(line)
    _write_file(line)


# ── Helpers privados ──────────────────────────────────────────────────────────

def _format(event: str, details: str) -> str:
    """Retorna a linha formatada segundo o padrão normativo da Seção 8."""
    ts = datetime.now().strftime("%H:%M:%S.") + \
        f"{datetime.now().microsecond // 1000:03d}"
    # Recalcula o timestamp em uma única chamada para evitar inconsistência
    # entre horas e milissegundos ao cruzar o segundo.
    now = datetime.now()
    ts = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
    return f"[{ts}] [{_DEVICE}] [{event}] {details}"


def _print(line: str) -> None:
    """Imprime a linha no terminal com flush imediato."""
    print(line, flush=True)


def _write_file(line: str) -> None:
    """Acrescenta a linha ao arquivo de log, ignorando erros de I/O."""
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        # Não interromper o encaminhamento por falha de escrita em disco.
        print(f"[AVISO] Falha ao gravar log em {_LOG_FILE}: {exc}",
              file=sys.stderr, flush=True)
