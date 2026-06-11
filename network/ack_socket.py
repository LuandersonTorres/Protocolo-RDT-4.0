# -*- coding: utf-8 -*-
"""
network/ack_socket.py — Socket UDP do canal de ACKs do Simulador B.

Responsabilidades:
  - Abrir e fechar o socket de ACKs.
  - Receber datagramas enviados por C (porta PORT_B_ACK).
  - Encaminhar datagramas para A (porta PORT_A_ACK).

Este módulo NÃO decide se o ACK será ou não encaminhado; essa decisão
pertence ao Forwarder (forwarder.py).
"""

import socket
from typing import Tuple

from utils.constants import PORT_B_ACK, PORT_A_ACK

# ACK tem sempre 7 bytes; margem de 1 byte extra para rejeição pelo
# desserializador (Seção 6.2).
_RECV_BUFFER: int = 8


class AckSocket:
    """Encapsula o socket UDP responsável pelo tráfego de ACKs (C ↔ A via B).

    O socket realiza bind em PORT_B_ACK (9002) para receber ACKs de C e
    envia para o IP de destino na PORT_A_ACK (9003).

    Args:
        host_a: Endereço IP (ou hostname) da máquina A.
        bind_host: Endereço local em que o socket fará bind (padrão "").
    """

    def __init__(self, host_a: str, bind_host: str = "") -> None:
        self._host_a = host_a
        self._bind_host = bind_host
        self._sock: socket.socket = self._create()

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def _create(self) -> socket.socket:
        """Cria e configura o socket UDP, realiza o bind em PORT_B_ACK."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._bind_host, PORT_B_ACK))
        return sock

    def close(self) -> None:
        """Fecha o socket, liberando a porta."""
        self._sock.close()

    # ── Operações de rede ─────────────────────────────────────────────────────

    def receive(self) -> Tuple[bytes, Tuple[str, int]]:
        """Bloqueia até receber um datagrama de C.

        Returns:
            Tupla (dados_brutos, endereço_origem) onde endereço_origem é
            (ip, porta).
        """
        return self._sock.recvfrom(_RECV_BUFFER)

    def forward_to_a(self, ack: bytes) -> None:
        """Envia *ack* para A na PORT_A_ACK (9003).

        Args:
            ack: Bytes brutos do datagrama a encaminhar (sem modificação).
        """
        self._sock.sendto(ack, (self._host_a, PORT_A_ACK))
