# -*- coding: utf-8 -*-
"""
network/forwarder.py — Núcleo de encaminhamento do Simulador B (RDT 4.0).

Responsabilidades:
  - Receber datagramas de qualquer um dos dois canais (dados / ACKs) via
    select() não-bloqueante para evitar starvation de um canal pelo outro.
  - Invocar os pontos de extensão process_packet() e process_ack() antes de
    encaminhar, permitindo que a Pessoa 4 injete a lógica do menu de falhas
    sem modificar esta classe.
  - Interpretar o datagrama (via rdt_utils) somente para fins de log.
  - Emitir o log [FW] no formato normativo da Seção 8.
  - NÃO alterar seq_num, ack_num, flags nem checksum.

Ponto de extensão (Pessoa 4):
  Substituir as funções process_packet() e process_ack() neste módulo pela
  implementação do menu de falhas.  A assinatura deve ser mantida:

      def process_packet(packet: bytes) -> bytes | None
      def process_ack(ack: bytes)     -> bytes | None

  Retornar None equivale a DROPAR o datagrama.
  Retornar bytes (possivelmente modificados) equivale a encaminhar.
"""
import select
import time
from typing import Optional

import rdt_utils
from network.ack_socket import AckSocket
from network.data_socket import DataSocket
from utils.constants import FLAG_ACK, ATRASO_B_MS
from utils.logger import log

# ── Pontos de extensão (substituídos pela Pessoa 4) ───────────────────────────


def process_packet(packet: bytes) -> Optional[bytes]:
    """
    Simula falhas em pacotes de dados enviados por A.

    Opções:
    1 - Encaminhar normalmente
    2 - Corromper pacote
    3 - Atrasar pacote
    4 - Dropar pacote

    Retorna:
        bytes -> pacote encaminhado para C
        None  -> pacote descartado
    """

    print("\n===== MENU PACOTE =====")
    print("1 - Encaminhar normalmente")
    print("2 - Corromper pacote")
    print("3 - Atrasar pacote")
    print("4 - Dropar pacote")
    print("=======================")

    opcao = input("Escolha: ")

    if opcao == "1":
        print("[B] Encaminhando normalmente")
        return packet

    elif opcao == "2":
        print("[B] Corrompendo pacote")

        pacote_corrompido = bytearray(packet)

        if len(pacote_corrompido) > 0:
            pacote_corrompido[-1] ^= 0xFF

        return bytes(pacote_corrompido)

    elif opcao == "3":
        print(f"[B] Atrasando pacote por {ATRASO_B_MS} ms")

        time.sleep(ATRASO_B_MS / 1000)

        return packet

    elif opcao == "4":
        print("[B] Pacote descartado")
        return None

    else:
        print("[B] Opção inválida -> encaminhando normalmente")
        return packet


def process_ack(ack: bytes) -> Optional[bytes]:
    """
    Simula falhas em ACKs enviados por C.

    Opções:
    1 - Encaminhar normalmente
    2 - Corromper ACK
    3 - Atrasar ACK
    4 - Dropar ACK

    Retorna:
        bytes -> ACK encaminhado para A
        None  -> ACK descartado
    """

    print("\n===== MENU ACK =====")
    print("1 - Encaminhar normalmente")
    print("2 - Corromper ACK")
    print("3 - Atrasar ACK")
    print("4 - Dropar ACK")
    print("====================")

    opcao = input("Escolha: ")

    if opcao == "1":
        print("[B] ACK encaminhado normalmente")
        return ack

    elif opcao == "2":
        print("[B] Corrompendo ACK")

        ack_corrompido = bytearray(ack)

        if len(ack_corrompido) > 0:
            ack_corrompido[-1] ^= 0xFF

        return bytes(ack_corrompido)

    elif opcao == "3":
        print(f"[B] Atrasando ACK por {ATRASO_B_MS} ms")

        time.sleep(ATRASO_B_MS / 1000)

        return ack

    elif opcao == "4":
        print("[B] ACK descartado")
        return None

    else:
        print("[B] Opção inválida -> encaminhando normalmente")
        return ack


# ── Classe principal ──────────────────────────────────────────────────────────


class Forwarder:
    """Orquestra o encaminhamento bidirecional entre A e C.

    Utiliza select() com timeout para monitorar os dois sockets
    simultaneamente, garantindo que nenhum canal monopolize a CPU.

    Args:
        data_sock: Socket de dados já configurado (bind em 9000).
        ack_sock:  Socket de ACKs já configurado (bind em 9002).
        select_timeout: Intervalo máximo de espera no select(), em segundos.
                        Valor baixo mantém o laço responsivo a sinais
                        (ex.: KeyboardInterrupt).
    """

    _SELECT_TIMEOUT: float = 0.5  # segundos

    def __init__(self, data_sock: DataSocket, ack_sock: AckSocket,
                 select_timeout: float = _SELECT_TIMEOUT) -> None:
        self._data_sock = data_sock
        self._ack_sock = ack_sock
        self._select_timeout = select_timeout

    # ── Laço principal ────────────────────────────────────────────────────────

    def run(self) -> None:
        """Mantém o simulador em execução contínua até KeyboardInterrupt."""
        log("FW", "Simulador B iniciado — aguardando datagramas...")
        try:
            while True:
                self._step()
        except KeyboardInterrupt:
            log("FW", "Simulador B encerrado pelo operador.")

    # ── Passo único do laço ───────────────────────────────────────────────────

    def _step(self) -> None:
        """Aguarda atividade em qualquer um dos sockets e despacha."""
        readable, _, _ = select.select(
            [self._data_sock._sock, self._ack_sock._sock],
            [],
            [],
            self._select_timeout,
        )
        for sock in readable:
            if sock is self._data_sock._sock:
                self._handle_packet()
            elif sock is self._ack_sock._sock:
                self._handle_ack()

    # ── Tratamento de pacotes de dados (A → C) ────────────────────────────────

    def _handle_packet(self) -> None:
        """Recebe um pacote de A, aplica process_packet() e encaminha para C."""
        raw, _ = self._data_sock.receive()

        processed: Optional[bytes] = process_packet(raw)

        action_label, seq_info = self._inspect_packet(raw)

        if processed is None:
            log("FW", f"{seq_info} | ACAO=DROP -> descartado")
            return

        self._data_sock.forward_to_c(processed)
        log("FW", f"{seq_info} | ACAO={action_label} -> encaminhado para C")

    # ── Tratamento de ACKs (C → A) ────────────────────────────────────────────

    def _handle_ack(self) -> None:
        """Recebe um ACK de C, aplica process_ack() e encaminha para A."""
        raw, _ = self._ack_sock.receive()

        processed: Optional[bytes] = process_ack(raw)

        action_label, ack_info = self._inspect_ack(raw)

        if processed is None:
            log("FW", f"{ack_info} | ACAO=DROP -> descartado")
            return

        self._ack_sock.forward_to_a(processed)
        log("FW", f"{ack_info} | ACAO={action_label} -> encaminhado para A")

    # ── Inspeção para fins de log (sem alterar o datagrama) ───────────────────

    @staticmethod
    def _inspect_packet(raw: bytes) -> tuple:
        """Extrai informações de log do pacote de dados.

        Retorna (label_acao, descricao_seq).  Em caso de datagrama malformado
        emite log ER e usa valores de fallback — o encaminhamento continuará
        normalmente, pois a detecção de erros é responsabilidade de C.

        Returns:
            Tupla (action_label: str, seq_info: str).
        """
        try:
            pkt = rdt_utils.desserializar(raw)
            seq_info = (
                f"SEQ={pkt['seq_num']} | FLAGS=0x{pkt['flags']:02X} "
                f"| LEN={pkt['data_len']}"
            )
        except ValueError as exc:
            log("ER", f"datagrama de dados malformado: {exc}")
            seq_info = "SEQ=? | FLAGS=? | LEN=?"
        return "NORMAL", seq_info

    @staticmethod
    def _inspect_ack(raw: bytes) -> tuple:
        """Extrai informações de log do ACK.

        Retorna (label_acao, descricao_ack).  Em caso de datagrama malformado
        emite log ER e usa valores de fallback.

        Returns:
            Tupla (action_label: str, ack_info: str).
        """
        try:
            pkt = rdt_utils.desserializar(raw)
            if pkt['flags'] == FLAG_ACK:
                ack_info = f"ACK={pkt['ack_num']}"
            else:
                ack_info = f"ACK=? | FLAGS=0x{pkt['flags']:02X} (nao-ACK)"
        except ValueError as exc:
            log("ER", f"datagrama de ACK malformado: {exc}")
            ack_info = "ACK=?"
        return "NORMAL", ack_info
