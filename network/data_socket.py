# -*- coding: utf-8 -*-
"""
network/data_socket.py — Socket UDP do canal de dados do Simulador B.

Responsabilidades:
  - Abrir e fechar o socket de dados.
  - Receber datagramas enviados por A (porta PORT_B_DADOS).
  - Encaminhar datagramas para C (porta PORT_C_DADOS).

Este módulo NÃO decide se o datagrama será ou não encaminhado; essa decisão
pertence ao Forwarder (forwarder.py).
"""

import socket
from typing import Tuple

from utils.constants import PORT_B_DADOS, PORT_C_DADOS

# Tamanho máximo de recepção: 7 bytes de cabeçalho + 1 400 bytes de payload
# + margem de 1 byte extra para que desserializar() rejeite datagramas com
# bytes excedentes (conforme Seção 6.2).
_RECV_BUFFER: int = 1408


class DataSocket:
    """Encapsula o socket UDP responsável pelo tráfego de dados (A ↔ C via B).

    O socket realiza bind em PORT_B_DADOS (9000) para receber pacotes de A
    e envia para o IP de destino na PORT_C_DADOS (9001).

    Args:
        host_c: Endereço IP (ou hostname) da máquina C.
        bind_host: Endereço local em que o socket fará bind (padrão "").
    """

    def __init__(self, host_c: str, bind_host: str = "") -> None:
        self._host_c = host_c
        self._bind_host = bind_host
        self._sock: socket.socket = self._create()

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def _create(self) -> socket.socket:
        """Cria e configura o socket UDP, realiza o bind em PORT_B_DADOS."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._bind_host, PORT_B_DADOS))
        return sock

    def close(self) -> None:
        """Fecha o socket, liberando a porta."""
        self._sock.close()

    # ── Operações de rede ─────────────────────────────────────────────────────

    def receive(self) -> Tuple[bytes, Tuple[str, int]]:
        """Bloqueia até receber um datagrama de A.

        Returns:
            Tupla (dados_brutos, endereço_origem) onde endereço_origem é
            (ip, porta).
        """
        return self._sock.recvfrom(_RECV_BUFFER)

    def forward_to_c(self, packet: bytes) -> None:
        """Envia *packet* para C na PORT_C_DADOS (9001).

        Args:
            packet: Bytes brutos do datagrama a encaminhar (sem modificação).
        """
        self._sock.sendto(packet, (self._host_c, PORT_C_DADOS))
