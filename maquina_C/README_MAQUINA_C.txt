MÁQUINA C — DESTINATÁRIO RDT 4.0

Arquivos novos entregues:
- maquina_C.py        -> código da Máquina C
- rdt_constants.py    -> cópia das constantes usadas pelo grupo
- rdt_utils.py        -> cópia dos utilitários usados pelo grupo

Como rodar em teste local, tudo no mesmo computador:

1) Terminal 1 — Máquina C:
   cd maquina_C
   python maquina_C.py 127.0.0.1

2) Terminal 2 — Máquina B já feita:
   python main.py 127.0.0.1 127.0.0.1

3) Terminal 3 — Máquina A:
   python maquina_A_sender.py 127.0.0.1

Fluxo de portas:
- A envia dados para B:9000
- B encaminha dados para C:9001
- C envia ACK para B:9002
- B encaminha ACK para A:9003

Comportamento da C:
- Se o datagrama for malformado: descarta e NÃO envia ACK.
- Se o checksum estiver errado: descarta e reenvia o último ACK válido.
- Se o pacote estiver fora de ordem/duplicado: descarta e reenvia o último ACK válido.
- Se o pacote estiver correto e em ordem: aceita, acumula payload e envia ACK cumulativo.
- Se vier FIN no último pacote: mostra a mensagem completa recebida.
