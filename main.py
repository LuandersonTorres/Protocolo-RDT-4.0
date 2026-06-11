# -*- coding: utf-8 -*-
"""
main.py — Ponto de entrada do Simulador B (RDT 4.0).

Uso:
    python main.py [IP_A] [IP_C]

    IP_A  — endereço da Máquina A para envio de ACKs  (padrão: 127.0.0.1)
    IP_C  — endereço da Máquina C para envio de dados  (padrão: 127.0.0.1)

Exemplos:
    python main.py                         # teste local (tudo em 127.0.0.1)
    python main.py 192.168.1.10 192.168.1.20
    python main.py 192.168.1.10            # C assume o mesmo IP que A

Fluxo de dados:
    A → B:9000 → C:9001   (pacotes de dados)
    C → B:9002 → A:9003   (ACKs)

Subir na ordem recomendada pela Seção 10.3:
    1) C  (escuta 9001)
    2) B  (este script — escuta 9000 e 9002)
    3) A  (interface de envio)
"""

import sys

from network.ack_socket import AckSocket
from network.data_socket import DataSocket
from network.forwarder import Forwarder
from utils.logger import log


def _parse_args() -> tuple:
    """Lê os endereços de A e C da linha de comando.

    Returns:
        Tupla (host_a: str, host_c: str).
    """
    host_a = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    host_c = sys.argv[2] if len(sys.argv) > 2 else host_a
    return host_a, host_c


def main() -> None:
    """Inicializa os sockets e inicia o laço de encaminhamento."""
    host_a, host_c = _parse_args()

    log("FW", f"Configuração: host_A={host_a} | host_C={host_c}")
    log("FW", "Abrindo sockets UDP...")

    data_sock = DataSocket(host_c=host_c)
    ack_sock = AckSocket(host_a=host_a)

    log("FW", "Bind concluído: dados em :9000 | ACKs em :9002")

    forwarder = Forwarder(data_sock=data_sock, ack_sock=ack_sock)

    try:
        forwarder.run()
    finally:
        data_sock.close()
        ack_sock.close()
        log("FW", "Sockets fechados. Encerrando.")


if __name__ == "__main__":
    main()
