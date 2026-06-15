# -*- coding: utf-8 -*-
"""
maquina_C.py — Máquina C / Destinatário do RDT 4.0 em Python.

Uso:
    python maquina_C.py [IP_B]

    IP_B — endereço da Máquina B para envio dos ACKs (padrão: 127.0.0.1)

Fluxo esperado do trabalho:
    A → B:9000 → C:9001   (pacotes de dados)
    C → B:9002 → A:9003   (ACKs)

Ordem recomendada para testar:
    1) python maquina_C.py [IP_B]
    2) python main.py [IP_A] [IP_C]       # Máquina B já feita
    3) subir a Máquina A

Interface Web:
    Esta versão também abre um servidor WebSocket em ws://127.0.0.1:8081
    para que index_C.html mostre os logs em tempo real (mesmo padrão usado
    na interface da Máquina A, mas em Python).

Esta implementação NÃO altera os arquivos da Máquina B.
Ela só usa as mesmas constantes e utilitários normativos do protocolo.
"""

import asyncio
import socket
import sys
import threading
from datetime import datetime

import websockets

from rdt_constants import (
    ENCODING,
    FLAG_ACK,
    FLAG_DATA,
    FLAG_FIN,
    HEADER_SIZE,
    PORT_B_ACK,
    PORT_C_DADOS,
    SEQ_INICIAL,
)
from rdt_utils import (
    checksum_ok,
    criar_ack,
    desserializar,
    prox,
    serializar,
)

# Tamanho máximo esperado: cabeçalho de 7 bytes + payload de 1400 bytes,
# com 1 byte extra para permitir que desserializar() detecte datagrama excedente.
_RECV_BUFFER = 1408
_LOG_FILE = "rdt_log_C.txt"

# Porta do servidor WebSocket usado pela interface web (index_C.html)
PORT_WEBSOCKET = 8081

# ---------------------------------------------------------------------------
# Infraestrutura de WebSocket — transmite os logs para o navegador
# ---------------------------------------------------------------------------
_clientes_ws: set = set()
_ws_loop = None


async def _ws_handler(websocket):
    """Mantém a conexão aberta e registra o cliente para receber logs."""
    _clientes_ws.add(websocket)
    try:
        async for _ in websocket:
            # A interface da Máquina C é apenas de leitura (não envia comandos).
            pass
    finally:
        _clientes_ws.discard(websocket)


async def _ws_main():
    global _ws_loop
    _ws_loop = asyncio.get_running_loop()
    async with websockets.serve(_ws_handler, "127.0.0.1", PORT_WEBSOCKET):
        await asyncio.Future()  # roda para sempre


def iniciar_servidor_web() -> None:
    """Inicia o servidor WebSocket numa thread separada (não bloqueia o UDP)."""
    thread = threading.Thread(target=lambda: asyncio.run(_ws_main()), daemon=True)
    thread.start()


def _broadcast(linha: str) -> None:
    """Envia uma linha de log para todos os navegadores conectados."""
    if _ws_loop is None or not _clientes_ws:
        return

    async def _enviar():
        mortos = []
        for ws in _clientes_ws:
            try:
                await ws.send(linha)
            except Exception:
                mortos.append(ws)
        for ws in mortos:
            _clientes_ws.discard(ws)

    asyncio.run_coroutine_threadsafe(_enviar(), _ws_loop)


def log(evento: str, detalhes: str) -> None:
    """Mostra o passo a passo no terminal, salva em rdt_log_C.txt e transmite via WebSocket."""
    now = datetime.now()
    ts = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
    linha = f"[{ts}] [C] [{evento.upper()}] {detalhes}"
    print(linha, flush=True)
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")
    except OSError:
        # Erro de log em arquivo não deve derrubar o protocolo.
        pass
    _broadcast(linha)


class MaquinaC:
    """Destinatário Go-Back-N do RDT 4.0.

    Regras principais implementadas:
      - aceita apenas o pacote com seq_num igual ao esperado;
      - envia ACK cumulativo do último pacote recebido em ordem;
      - em pacote fora de ordem ou duplicado, descarta e reenvia o último ACK;
      - em datagrama malformado (ER), descarta sem enviar ACK;
      - em checksum inválido (CE), descarta e reenvia o último ACK;
      - usa FIN (DATA|FIN = 0x90) para saber quando a mensagem terminou.
    """

    def __init__(self, host_b: str = "127.0.0.1", bind_host: str = "") -> None:
        self.host_b = host_b
        self.bind_host = bind_host
        self.expected_seq = SEQ_INICIAL
        self.last_in_order = (SEQ_INICIAL - 1) % 256
        self.buffer_mensagem = bytearray()
        self.sock = self._criar_socket()

    def _criar_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.bind_host, PORT_C_DADOS))
        return sock

    def close(self) -> None:
        self.sock.close()

    def run(self) -> None:
        log("INI", f"Máquina C iniciada — escutando dados em :{PORT_C_DADOS}")
        log("INI", f"ACKs serão enviados para B em {self.host_b}:{PORT_B_ACK}")
        log("EST", f"Esperando SEQ inicial = {self.expected_seq}")

        try:
            while True:
                raw, addr = self.sock.recvfrom(_RECV_BUFFER)
                self._tratar_datagrama(raw, addr)
        except KeyboardInterrupt:
            log("FIM", "Máquina C encerrada pelo operador.")
        finally:
            self.close()

    def _tratar_datagrama(self, raw: bytes, addr) -> None:
        log("RX", f"Datagrama recebido de {addr[0]}:{addr[1]} | bytes={len(raw)}")

        # Etapa 1: formato. Se falhar aqui, é ER e NÃO envia ACK.
        try:
            pkt = desserializar(raw)
        except ValueError as exc:
            log("ER", f"Datagrama malformado descartado sem ACK | motivo={exc}")
            return

        # Etapa 2: checksum. Se falhar aqui, é CE e reenvia o último ACK.
        if not checksum_ok(pkt):
            log("CE", f"Checksum inválido | SEQ={pkt['seq_num']} descartado")
            self._reenviar_ultimo_ack("checksum inválido")
            return

        # C é destinatário de dados; ACK recebido nesta porta não faz parte do fluxo.
        if pkt["flags"] == FLAG_ACK:
            log("IGN", f"ACK recebido na porta de dados | ACK={pkt['ack_num']} descartado")
            return

        if not (pkt["flags"] & FLAG_DATA):
            log("IGN", f"Pacote sem FLAG_DATA descartado | FLAGS=0x{pkt['flags']:02X}")
            return

        seq = pkt["seq_num"]
        flags = pkt["flags"]
        data_len = pkt["data_len"]

        log("PKT", f"SEQ={seq} | esperado={self.expected_seq} | FLAGS=0x{flags:02X} | LEN={data_len}")

        # Go-Back-N receiver: só aceita exatamente o próximo esperado.
        if seq == self.expected_seq:
            self._aceitar_em_ordem(pkt)
        else:
            log(
                "OOO",
                f"Pacote fora de ordem/duplicado descartado | recebido={seq} | esperado={self.expected_seq}",
            )
            self._reenviar_ultimo_ack("fora de ordem ou duplicado")

    def _aceitar_em_ordem(self, pkt: dict) -> None:
        seq = pkt["seq_num"]
        self.buffer_mensagem.extend(pkt["data"])
        self.last_in_order = seq
        self.expected_seq = prox(self.expected_seq)

        log("OK", f"Pacote aceito em ordem | SEQ={seq} | próximo esperado={self.expected_seq}")
        self._enviar_ack(seq, "pacote aceito")

        if pkt["flags"] & FLAG_FIN:
            self._finalizar_mensagem()

    def _finalizar_mensagem(self) -> None:
        dados = bytes(self.buffer_mensagem)
        try:
            texto = dados.decode(ENCODING)
        except UnicodeDecodeError:
            texto = dados.decode(ENCODING, errors="replace")

        log("MSG", f"Mensagem completa recebida ({len(dados)} bytes): {texto!r}")
        print("\n========== MENSAGEM RECEBIDA EM C ==========")
        print(texto)
        print("============================================\n")
        _broadcast(f"__MSG__{texto}")

        # Limpa apenas o conteúdo da mensagem. O número de sequência continua,
        # porque a sessão RDT pode seguir com novos pacotes depois do FIN.
        self.buffer_mensagem.clear()

    def _reenviar_ultimo_ack(self, motivo: str) -> None:
        self._enviar_ack(self.last_in_order, f"re-ACK por {motivo}")

    def _enviar_ack(self, ack_num: int, motivo: str) -> None:
        ack_pkt = criar_ack(ack_num)
        ack_bytes = serializar(ack_pkt)
        self.sock.sendto(ack_bytes, (self.host_b, PORT_B_ACK))
        log("ACK", f"ACK={ack_num} enviado para B:{PORT_B_ACK} | motivo={motivo}")


def _parse_args() -> str:
    return sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"


def main() -> None:
    host_b = _parse_args()
    iniciar_servidor_web()
    print(f"[C] Interface web disponível — abra index_C.html no navegador")
    print(f"[C] Servidor WebSocket em ws://127.0.0.1:{PORT_WEBSOCKET}\n")
    maquina = MaquinaC(host_b=host_b)
    maquina.run()


if __name__ == "__main__":
    main()
