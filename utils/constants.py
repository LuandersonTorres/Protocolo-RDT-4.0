# -*- coding: utf-8 -*-
"""
utils/constants.py — Reexporta as constantes normativas do protocolo RDT 4.0.

Centraliza a importação para o pacote B; todos os módulos internos importam
daqui, nunca diretamente de rdt_constants, facilitando eventual substituição
do módulo de origem sem tocar em vários arquivos.
"""

from rdt_constants import (  # noqa: F401  (reexportação intencional)
    WINDOW_SIZE,
    SEQ_MOD,
    SEQ_INICIAL,
    HEADER_SIZE,
    MAX_PAYLOAD,
    TIMEOUT_MS,
    ATRASO_B_MS,
    FLAG_DATA,
    FLAG_ACK,
    FLAG_FIN,
    PORT_B_DADOS,
    PORT_C_DADOS,
    PORT_B_ACK,
    PORT_A_ACK,
    ENCODING,
)
