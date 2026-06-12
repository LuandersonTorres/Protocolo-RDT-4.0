# -*- coding: utf-8 -*-
"""
rdt_constants.py — Constantes globais do protocolo RDT 4.0 (Grupo 3).
Fonte normativa: RDT4_Especificacao.pdf, Secao 11.
NAO alterar valores sem combinar com todo o grupo: todas as maquinas
(A, B e C) devem usar exatamente estes valores.
"""

WINDOW_SIZE = 5        # Tamanho da janela deslizante (Go-Back-N)
SEQ_MOD     = 256      # Modulo do espaco de sequencia (uint8)
SEQ_INICIAL = 0        # Sequencia inicial (alteravel SO no teste I14)
HEADER_SIZE = 7        # Bytes do cabecalho fixo
MAX_PAYLOAD = 1400     # Maximo de bytes de payload por pacote
TIMEOUT_MS  = 2000     # Timeout do timer unico de A (ms)
ATRASO_B_MS = 3000     # Atraso aplicado pelo menu de B (ms)

FLAG_DATA = 0x80       # Pacote de dados (fragmento intermediario)
FLAG_ACK  = 0x40       # Pacote e um ACK puro
FLAG_FIN  = 0x10       # Ultimo fragmento da mensagem (usado como DATA|FIN = 0x90)

FLAGS_VALIDAS = (0x80, 0x90, 0x40)   # Unicas combinacoes aceitas (Secao 3.2)

PORT_B_DADOS = 9000    # B escuta dados de A
PORT_C_DADOS = 9001    # C escuta dados de B
PORT_B_ACK   = 9002    # B escuta ACKs de C
PORT_A_ACK   = 9003    # A escuta ACKs de B

ENCODING = "utf-8"     # Codificacao texto <-> bytes
