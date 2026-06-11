# -*- coding: utf-8 -*-
"""
test_rdt_utils.py — Testes unitarios U1–U11 + vetores binarios V1–V5.
Fonte normativa: RDT4_Especificacao.pdf, Secoes 9 e 10.1.

Como executar:
    python3 test_rdt_utils.py          (nao precisa de nada alem do Python 3)
    pytest test_rdt_utils.py           (opcional, se tiver pytest)

CADA PESSOA deve rodar este script contra os utilitarios da SUA linguagem
antes de integrar. Se sua implementacao nao for em Python, reproduza pelo
menos os vetores V1–V5 byte a byte (Secao 9) — eles garantem a
interoperabilidade entre linguagens.
"""

import random
import sys

from rdt_constants import HEADER_SIZE, MAX_PAYLOAD
from rdt_utils import (checksum_internet, serializar, desserializar,
                       checksum_ok, criar_pacote, criar_ack,
                       validar_ack, dist, prox, ack_valido,
                       fragmentar_mensagem)


def _rejeitado(buf: bytes) -> bool:
    """Fluxo oficial em 2 etapas (Secoes 5.2/7.3): True se o datagrama for
    descartado, seja por formato invalido (ER) ou checksum invalido (CE)."""
    try:
        pkt = desserializar(buf)
    except ValueError:
        return True            # ER
    return not checksum_ok(pkt)  # CE se True

# ---------------------------------------------------------------------------
# Vetores binarios oficiais (Secao 9) — NAO ALTERAR
# ---------------------------------------------------------------------------
V1_BYTES = bytes.fromhex("000080EE03000A4F6C61206D756E646F21")  # dados seq=0 "Ola mundo!"
V1_CHECKSUM = 0xEE03
V2_BYTES = bytes.fromhex("000040BFFF0000")                        # ACK ack_num=0
V3_BYTES = bytes.fromhex("000740BFF80000")                        # ACK ack_num=7
V4_BYTES = bytes.fromhex("FF00900B3A0003616263")                  # DATA|FIN seq=255 "abc"
V5_ENTRADA = bytes([0x01, 0x02, 0x03, 0x04, 0x05])
V5_ESPERADO = 0xF6F9
V5B_ESPERADO = 0xFFFF                                             # entrada vazia


def test_u1_roundtrip():
    """U1 — desserializar(serializar(pkt)) == pkt, campo a campo."""
    rng = random.Random(1)
    for _ in range(500):
        dados = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 201)))
        pkt = criar_pacote(rng.randrange(256), dados,
                           ultimo_fragmento_da_mensagem=bool(rng.randrange(2)))
        assert desserializar(serializar(pkt)) == pkt
    ack = criar_ack(123)
    assert desserializar(serializar(ack)) == ack


def test_u2_checksum_integro():
    """U2 — verificar_checksum aceita pacote integro."""
    rng = random.Random(2)
    for _ in range(500):
        dados = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 201)))
        buf = serializar(criar_pacote(rng.randrange(256), dados))
        assert checksum_ok(desserializar(buf))
    assert checksum_ok(desserializar(serializar(criar_ack(0))))


def test_u3_checksum_corrompido():
    """U3 — TODA inversao de 1 bit e detectada (exaustivo no vetor V1 +
    aleatorio em 200 pacotes)."""
    for pos in range(len(V1_BYTES)):           # exaustivo: 17 bytes x 8 bits
        for bit in range(8):
            b = bytearray(V1_BYTES)
            b[pos] ^= (1 << bit)
            assert _rejeitado(bytes(b)), \
                f"corrupcao nao detectada: byte {pos}, bit {bit}"
    rng = random.Random(3)
    for _ in range(200):
        dados = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 101)))
        buf = bytearray(serializar(criar_pacote(rng.randrange(256), dados)))
        buf[rng.randrange(len(buf))] ^= (1 << rng.randrange(8))
        assert _rejeitado(bytes(buf))


def test_u4_flags_data():
    """U4 — dados: 0x80; ultimo fragmento da mensagem: 0x90."""
    assert criar_pacote(3, b"xyz")['flags'] == 0x80
    assert criar_pacote(3, b"xyz", ultimo_fragmento_da_mensagem=True)['flags'] == 0x90


def test_u5_flags_ack():
    """U5 — ACK puro: 0x40."""
    assert criar_ack(9)['flags'] == 0x40


def test_u6_tamanho_minimo():
    """U6 — ACK serializado tem exatamente 7 bytes (HEADER_SIZE)."""
    assert len(serializar(criar_ack(0))) == HEADER_SIZE == 7


def test_u7_payload_impar():
    """U7 — payload de tamanho impar (padding) passa em U2/U3."""
    pkt = criar_pacote(1, b"abc")
    buf = serializar(pkt)
    assert checksum_ok(desserializar(buf))
    b = bytearray(buf)
    b[-1] ^= 0x01
    assert _rejeitado(bytes(b))


def test_u8_ack_cumulativo():
    """U8 — criar_ack(5).ack_num == 5; validar_ack devolve o numero."""
    ack = criar_ack(5)
    assert ack['ack_num'] == 5
    assert validar_ack(serializar(ack)) == ('OK', 5)
    assert validar_ack(serializar(criar_ack(0))) == ('OK', 0)   # 0 e ACK valido do SEQ 0
    assert validar_ack(serializar(criar_pacote(1, b"x"))) == ('NAO_ACK', None)


def test_u9_desserializacao_estrita():
    """U9 — rejeitar (ER): truncado; byte extra; data_len=65535; flags=0x20;\n    ACK (0x40) com data_len > 0."""
    buf = serializar(criar_pacote(0, b"abc"))
    casos = []
    casos.append(buf[:-1])                       # truncado
    casos.append(buf + b"\x00")                  # byte extra
    grande = bytearray(buf); grande[5] = 0xFF; grande[6] = 0xFF
    casos.append(bytes(grande))                  # data_len = 65535 > MAX_PAYLOAD
    flags_ruim = bytearray(buf); flags_ruim[2] = 0x20
    casos.append(bytes(flags_ruim))              # flags invalidas (SYN reservado)
    ack_payload = {'seq_num': 0, 'ack_num': 3, 'flags': 0x40,
                   'checksum': 0, 'data_len': 2, 'data': b"xy"}
    ack_payload['checksum'] = checksum_internet(serializar(ack_payload))
    casos.append(serializar(ack_payload))        # ACK (0x40) com data_len > 0
    rejeitados = 0
    for c in casos:
        try:
            desserializar(c)
        except ValueError:
            rejeitados += 1                      # ER: descartar SEM ACK
    assert rejeitados == 5


def test_u10_vetores_binarios():
    """U10 — gerar e aceitar V1–V5 byte a byte (Secao 9)."""
    v1 = criar_pacote(0, "Ola mundo!".encode("utf-8"))
    assert serializar(v1) == V1_BYTES and v1['checksum'] == V1_CHECKSUM
    assert serializar(criar_ack(0)) == V2_BYTES
    assert serializar(criar_ack(7)) == V3_BYTES
    v4 = criar_pacote(255, b"abc", ultimo_fragmento_da_mensagem=True)
    assert serializar(v4) == V4_BYTES
    for v in (V1_BYTES, V2_BYTES, V3_BYTES, V4_BYTES):
        assert checksum_ok(desserializar(v))     # todos validos no fluxo de 2 etapas
    assert checksum_internet(V5_ENTRADA) == V5_ESPERADO
    assert checksum_internet(b"") == V5B_ESPERADO


def test_u11_aritmetica_modular():
    """U11 — identidades da Secao 7.1 (inicio de sessao e wrap-around)."""
    assert dist(0, 255) == 1
    assert dist(255, 0) == 255
    assert prox(255) == 0
    assert ack_valido(255, 0, 3) is False        # re-ACK inicial 255: ignorado por A
    assert ack_valido(1, 255, 4) is True         # janela cruzando o wrap 255 -> 0
    assert ack_valido(0, 0, 1) is True           # ACK do primeiro pacote
    assert ack_valido(1, 0, 1) is False          # ACK de pacote nao enviado: ignorado


def test_extra_fragmentacao():
    """R5/I13 — fragmentacao: blocos <= 1400, somente o ultimo com FIN."""
    msg = bytes(3000)
    frags = fragmentar_mensagem(msg)
    assert [len(b) for b, _ in frags] == [1400, 1400, 200]
    assert [u for _, u in frags] == [False, False, True]
    assert b"".join(b for b, _ in frags) == msg
    flags = [criar_pacote(i, b, ultimo_fragmento_da_mensagem=u)['flags']
             for i, (b, u) in enumerate(frags)]
    assert flags == [0x80, 0x80, 0x90]
    assert fragmentar_mensagem(b"oi") == [(b"oi", True)]


def test_extra_er_vs_ce():
    """5.2/7.3 — ER (malformado, sem ACK) e CE (corrompido, com re-ACK) sao
    distinguiveis pelo fluxo de duas etapas."""
    buf = serializar(criar_pacote(4, b"dados"))
    # ER: truncado -> desserializar levanta ValueError
    try:
        desserializar(buf[:-1])
        assert False, "malformado deveria levantar ValueError (ER)"
    except ValueError:
        pass
    # CE: payload corrompido -> bem formado, checksum_ok False
    b = bytearray(buf)
    b[9] ^= 0xFF
    pkt = desserializar(bytes(b))      # desserializa sem erro (formato ok)
    assert not checksum_ok(pkt)        # mas o checksum acusa a corrupcao
    assert validar_ack(buf[:-1]) == ('ER', None)
    ack_corrompido = bytearray(serializar(criar_ack(2)))
    ack_corrompido[4] ^= 0x01
    assert validar_ack(bytes(ack_corrompido)) == ('CE', None)


TESTES = [
    test_u1_roundtrip, test_u2_checksum_integro, test_u3_checksum_corrompido,
    test_u4_flags_data, test_u5_flags_ack, test_u6_tamanho_minimo,
    test_u7_payload_impar, test_u8_ack_cumulativo,
    test_u9_desserializacao_estrita, test_u10_vetores_binarios,
    test_u11_aritmetica_modular, test_extra_fragmentacao,
    test_extra_er_vs_ce,
]

if __name__ == "__main__":
    falhas = 0
    for t in TESTES:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except AssertionError as e:
            falhas += 1
            print(f"[FAIL] {t.__name__}: {e}")
    total = len(TESTES)
    print(f"\n{total - falhas}/{total} testes passaram.")
    sys.exit(1 if falhas else 0)
