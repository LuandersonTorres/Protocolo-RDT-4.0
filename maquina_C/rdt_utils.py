# -*- coding: utf-8 -*-
"""
rdt_utils.py — Funcoes utilitarias do protocolo RDT 4.0 (Grupo 3).
Fonte normativa: RDT4_Especificacao.pdf, Secoes 3 a 7.1.

Conteudo:
  - checksum_internet(dados)            Secao 5.1 (carry dobrado DENTRO do laco)
  - serializar(pkt) / desserializar(b)  Secoes 6.1 e 6.2 (desserializacao ESTRITA)
  - checksum_ok(pkt)                    Secao 5.2 (OFICIAL: zerar e recalcular; 2 etapas ER/CE)
  - criar_pacote / criar_ack            Secoes 3.4 e 4
  - validar_ack(buf)                    Secao 4 (usado por A)
  - dist / prox / ack_valido            Secao 7.1 (aritmetica modular OBRIGATORIA)
  - fragmentar_mensagem(dados)          Regra R5 + Secao 3.3 (FIN delimita a mensagem)

O pacote e representado como dict com as chaves:
  seq_num, ack_num, flags, checksum, data_len (int) e data (bytes).
"""

import struct

from rdt_constants import (SEQ_MOD, HEADER_SIZE, MAX_PAYLOAD,
                           FLAG_DATA, FLAG_ACK, FLAG_FIN, FLAGS_VALIDAS)

# Formato do cabecalho: big-endian, 3 x uint8 + 2 x uint16 = 7 bytes (Secao 3.1)
HEADER_FORMAT = '!BBBHH'
assert struct.calcsize(HEADER_FORMAT) == HEADER_SIZE


# ----------------------------------------------------------------------------
# CHECKSUM (Secao 5)
# ----------------------------------------------------------------------------
def checksum_internet(dados: bytes) -> int:
    """Internet Checksum de 16 bits (complemento de 1).

    ATENCAO: o carry e dobrado DENTRO do laco, a cada soma. Trata-lo uma
    unica vez ao final produz checksums incompativeis (Secao 5.1).
    """
    soma = 0
    n = len(dados)
    i = 0
    while i + 1 < n:
        soma += (dados[i] << 8) | dados[i + 1]
        if soma > 0xFFFF:
            soma = (soma & 0xFFFF) + 1
        i += 2
    if n % 2 == 1:                       # byte impar final: padding 0x00 a direita
        soma += dados[-1] << 8
        if soma > 0xFFFF:
            soma = (soma & 0xFFFF) + 1
    return (~soma) & 0xFFFF


# ----------------------------------------------------------------------------
# SERIALIZACAO / DESSERIALIZACAO (Secao 6)
# ----------------------------------------------------------------------------
def serializar(pkt: dict) -> bytes:
    """Converte o pacote em bytes prontos para envio via UDP (Secao 6.1)."""
    return struct.pack(HEADER_FORMAT, pkt['seq_num'], pkt['ack_num'],
                       pkt['flags'], pkt['checksum'], pkt['data_len']) + pkt['data']


def desserializar(buf: bytes) -> dict:
    """Desserializacao ESTRITA (Secao 6.2). Levanta ValueError (-> log ER)
    para qualquer datagrama malformado. NUNCA aceitar bytes extras."""
    if len(buf) < HEADER_SIZE:
        raise ValueError("pacote menor que o cabecalho (7 bytes)")
    seq, ack, flags, cs, dlen = struct.unpack_from(HEADER_FORMAT, buf, 0)
    if dlen > MAX_PAYLOAD:
        raise ValueError("data_len > MAX_PAYLOAD")
    if len(buf) != HEADER_SIZE + dlen:
        raise ValueError("tamanho do datagrama != 7 + data_len")
    if flags not in FLAGS_VALIDAS:
        raise ValueError("flags invalidas (aceitas: 0x80, 0x90, 0x40)")
    if flags == FLAG_ACK and dlen != 0:
        raise ValueError("ACK nao carrega payload (flags=0x40 exige data_len=0)")
    return {'seq_num': seq, 'ack_num': ack, 'flags': flags,
            'checksum': cs, 'data_len': dlen, 'data': buf[HEADER_SIZE:]}


def checksum_ok(pkt: dict) -> bool:
    """Verificacao OFICIAL (Secao 5.2): zera o campo checksum, recalcula e
    compara. Chamar SOMENTE apos desserializar() ter aceitado o datagrama.

    Fluxo obrigatorio em duas etapas (Secoes 5.2 e 7.3):
      1) desserializar(buf) levantou ValueError -> malformado -> log ER,
         descartar SEM enviar ACK;
      2) desserializou, mas checksum_ok(pkt) == False -> corrompido -> log CE;
         em C, descartar e re-ACKar o ultimo em ordem; em A, descartar o ACK.

    PROIBIDO verificar com checksum_internet(buf) == 0 — nao funciona com
    este layout de cabecalho (checksum em offset impar)."""
    zerado = struct.pack(HEADER_FORMAT, pkt['seq_num'], pkt['ack_num'],
                         pkt['flags'], 0, pkt['data_len']) + pkt['data']
    return checksum_internet(zerado) == pkt['checksum']


# ----------------------------------------------------------------------------
# CRIACAO DE PACOTES (Secoes 3.4 e 4)
# ----------------------------------------------------------------------------
def criar_pacote(seq: int, dados: bytes, ultimo_fragmento_da_mensagem: bool = False) -> dict:
    """Cria um pacote de dados. flags = 0x80 (fragmento intermediario) ou
    0x90 (ultimo/unico fragmento da mensagem — Secao 3.3)."""
    if not 0 <= seq < SEQ_MOD:
        raise ValueError("seq fora de 0..255")
    if len(dados) > MAX_PAYLOAD:
        raise ValueError("payload > MAX_PAYLOAD: fragmentar antes (R5)")
    flags = FLAG_DATA | (FLAG_FIN if ultimo_fragmento_da_mensagem else 0)
    pkt = {'seq_num': seq, 'ack_num': 0, 'flags': flags,
           'checksum': 0, 'data_len': len(dados), 'data': bytes(dados)}
    pkt['checksum'] = checksum_internet(serializar(pkt))   # calculado com campo em 0
    return pkt


def criar_ack(seq_recebido: int) -> dict:
    """Cria um ACK cumulativo confirmando o ultimo pacote recebido EM ORDEM."""
    if not 0 <= seq_recebido < SEQ_MOD:
        raise ValueError("ack_num fora de 0..255")
    ack = {'seq_num': 0, 'ack_num': seq_recebido, 'flags': FLAG_ACK,
           'checksum': 0, 'data_len': 0, 'data': b''}
    ack['checksum'] = checksum_internet(serializar(ack))
    return ack


def validar_ack(buf: bytes):
    """Validacao de ACK em A (Secao 4), em duas etapas.
    Retorna a tupla (status, ack_num):
      ('OK',      0..255) — ACK valido; usar com ack_valido() para avancar a janela
      ('ER',      None)   — datagrama malformado: log ER e descartar
      ('CE',      None)   — bem formado, checksum invalido: log CE e descartar
      ('NAO_ACK', None)   — valido, mas flags != 0x40: ignorar
    """
    try:
        ack = desserializar(buf)
    except ValueError:
        return ('ER', None)
    if not checksum_ok(ack):
        return ('CE', None)
    if ack['flags'] != FLAG_ACK:
        return ('NAO_ACK', None)
    return ('OK', ack['ack_num'])


# ----------------------------------------------------------------------------
# ARITMETICA MODULAR DA JANELA (Secao 7.1)
# ----------------------------------------------------------------------------
def dist(a: int, b: int) -> int:
    """Quantos passos de b ate a, no circulo 0..255. Em Python, % de negativo
    ja e nao-negativo; em Java/C/JS usar ((a-b) % 256 + 256) % 256."""
    return (a - b) % SEQ_MOD


def prox(s: int) -> int:
    """Proximo numero de sequencia (com wrap-around 255 -> 0)."""
    return (s + 1) % SEQ_MOD


def ack_valido(num_ack: int, send_base: int, next_seq_num: int) -> bool:
    """True se o ACK confirma algo dentro da janela pendente do remetente.
    NUNCA comparar numeros de sequencia com <, > ou >= diretamente."""
    return dist(num_ack, send_base) < dist(next_seq_num, send_base)


# ----------------------------------------------------------------------------
# FRAGMENTACAO DE MENSAGENS (Regra R5 + Secao 3.3)
# ----------------------------------------------------------------------------
def fragmentar_mensagem(dados: bytes):
    """Divide a mensagem em fragmentos de ate MAX_PAYLOAD bytes.
    Retorna lista de tuplas (fragmento: bytes, ultimo: bool) — o flag 'ultimo'
    deve ser passado a criar_pacote para marcar o FIN (0x90) no ultimo
    fragmento, permitindo a remontagem em C."""
    if len(dados) == 0:
        return [(b'', True)]
    blocos = [dados[i:i + MAX_PAYLOAD] for i in range(0, len(dados), MAX_PAYLOAD)]
    return [(b, i == len(blocos) - 1) for i, b in enumerate(blocos)]
