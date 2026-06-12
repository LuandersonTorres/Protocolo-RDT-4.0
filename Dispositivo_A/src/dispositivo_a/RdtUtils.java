package dispositivo_a;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * RdtUtils.java — Funcoes utilitarias do protocolo RDT 4.0 (Grupo 3).
 * Fonte normativa: RDT4_Especificacao.pdf, Secoes 3 a 7.1.
 *
 * Conteudo:
 *   - checksumInternet(dados)              Secao 5.1 (carry dobrado DENTRO do laco)
 *   - serializar / desserializar           Secoes 6.1 e 6.2 (desserializacao ESTRITA)
 *   - checksumOk(buf, pkt)                 Secao 5.2 (OFICIAL: zerar e recalcular)
 *   - criarPacote / criarAck               Secoes 3.4 e 4
 *   - validarAck(buf)                      Secao 4 (usado por A; distingue ER/CE)
 *   - dist / prox / ackValido              Secao 7.1 (aritmetica modular OBRIGATORIA)
 *   - fragmentarMensagem(dados)            Regra R5 + Secao 3.3 (FIN delimita a mensagem)
 *
 * Fluxo OBRIGATORIO de validacao em duas etapas (Secoes 5.2 e 7.3):
 *   1) desserializar(buf) lancou FormatoInvalidoException -> malformado ->
 *      log ER, descartar SEM enviar ACK;
 *   2) desserializou, mas checksumOk(buf, pkt) == false -> corrompido ->
 *      log CE; em C, descartar e re-ACKar o ultimo em ordem; em A, descartar o ACK.
 */
public final class RdtUtils {

    private RdtUtils() {}                       // nao instanciavel

    /** Datagrama malformado (Secao 6.2) — corresponde ao log ER. */
    public static class FormatoInvalidoException extends Exception {
        /**
		 * 
		 */
		private static final long serialVersionUID = 1L;

		public FormatoInvalidoException(String msg) { super(msg); }
    }

    /** Pacote RDT 4.0 (Secao 3.1). Campos como int sem sinal (0..255 / 0..65535). */
    public static class Pacote {
        public int seqNum;
        public int ackNum;
        public int flags;
        public int checksum;
        public int dataLen;
        public byte[] data = new byte[0];

        @Override public boolean equals(Object o) {
            if (!(o instanceof Pacote)) return false;
            Pacote p = (Pacote) o;
            return seqNum == p.seqNum && ackNum == p.ackNum && flags == p.flags
                && checksum == p.checksum && dataLen == p.dataLen
                && Arrays.equals(data, p.data);
        }
        @Override public int hashCode() {
            return 31 * (seqNum + 31 * (ackNum + 31 * flags)) + Arrays.hashCode(data);
        }
    }

    // ------------------------------------------------------------------------
    // CHECKSUM (Secao 5)
    // ------------------------------------------------------------------------

    /**
     * Internet Checksum de 16 bits (complemento de 1).
     * ATENCAO: o carry e dobrado DENTRO do laco, a cada soma. Trata-lo uma
     * unica vez ao final produz checksums incompativeis (Secao 5.1).
     * O "& 0xFF" e obrigatorio: byte em Java tem sinal.
     */
    public static int checksumInternet(byte[] dados) {
        int soma = 0;
        int n = dados.length;
        int i = 0;
        while (i + 1 < n) {
            soma += ((dados[i] & 0xFF) << 8) | (dados[i + 1] & 0xFF);
            if (soma > 0xFFFF) soma = (soma & 0xFFFF) + 1;
            i += 2;
        }
        if (n % 2 == 1) {                       // byte impar final: padding 0x00
            soma += (dados[n - 1] & 0xFF) << 8;
            if (soma > 0xFFFF) soma = (soma & 0xFFFF) + 1;
        }
        return (~soma) & 0xFFFF;
    }

    /**
     * Verificacao OFICIAL (Secao 5.2): zera o campo checksum (bytes 3-4) e
     * recalcula. Chamar SOMENTE apos desserializar(buf) ter aceitado o
     * datagrama (senao: log ER). PROIBIDO verificar com
     * checksumInternet(buf) == 0 — nao funciona com este layout de cabecalho.
     */
    public static boolean checksumOk(byte[] buf, Pacote p) {
        byte[] zerado = buf.clone();
        zerado[3] = 0;
        zerado[4] = 0;
        return checksumInternet(zerado) == p.checksum;
    }

    // ------------------------------------------------------------------------
    // SERIALIZACAO / DESSERIALIZACAO (Secao 6)
    // ------------------------------------------------------------------------

    /** Converte o pacote em bytes prontos para envio via UDP (Secao 6.1). */
    public static byte[] serializar(Pacote p) {
        ByteBuffer b = ByteBuffer.allocate(RdtConstants.HEADER_SIZE + p.dataLen)
                                 .order(ByteOrder.BIG_ENDIAN);
        b.put((byte) p.seqNum).put((byte) p.ackNum).put((byte) p.flags);
        b.putShort((short) p.checksum).putShort((short) p.dataLen).put(p.data);
        return b.array();
    }

    /**
     * Desserializacao ESTRITA (Secao 6.2). Lanca FormatoInvalidoException
     * (-> log ER) para qualquer datagrama malformado. NUNCA aceitar bytes
     * extras; ACK (0x40) exige data_len = 0.
     */
    public static Pacote desserializar(byte[] buf) throws FormatoInvalidoException {
        if (buf.length < RdtConstants.HEADER_SIZE)
            throw new FormatoInvalidoException("pacote menor que o cabecalho (7 bytes)");
        ByteBuffer b = ByteBuffer.wrap(buf).order(ByteOrder.BIG_ENDIAN);
        Pacote p = new Pacote();
        p.seqNum   = b.get() & 0xFF;
        p.ackNum   = b.get() & 0xFF;
        p.flags    = b.get() & 0xFF;
        p.checksum = b.getShort() & 0xFFFF;
        p.dataLen  = b.getShort() & 0xFFFF;
        if (p.dataLen > RdtConstants.MAX_PAYLOAD)
            throw new FormatoInvalidoException("data_len > MAX_PAYLOAD");
        if (buf.length != RdtConstants.HEADER_SIZE + p.dataLen)
            throw new FormatoInvalidoException("tamanho do datagrama != 7 + data_len");
        if (p.flags != 0x80 && p.flags != 0x90 && p.flags != 0x40)
            throw new FormatoInvalidoException("flags invalidas (aceitas: 0x80, 0x90, 0x40)");
        if (p.flags == RdtConstants.FLAG_ACK && p.dataLen != 0)
            throw new FormatoInvalidoException("ACK nao carrega payload (flags=0x40 exige data_len=0)");
        p.data = new byte[p.dataLen];
        b.get(p.data);
        return p;
    }

    // ------------------------------------------------------------------------
    // CRIACAO DE PACOTES (Secoes 3.4 e 4)
    // ------------------------------------------------------------------------

    /**
     * Cria um pacote de dados. flags = 0x80 (fragmento intermediario) ou
     * 0x90 (ultimo/unico fragmento da mensagem — Secao 3.3).
     */
    public static Pacote criarPacote(int seq, byte[] dados,
                                     boolean ultimoFragmentoDaMensagem) {
        if (seq < 0 || seq >= RdtConstants.SEQ_MOD)
            throw new IllegalArgumentException("seq fora de 0..255");
        if (dados.length > RdtConstants.MAX_PAYLOAD)
            throw new IllegalArgumentException("payload > MAX_PAYLOAD: fragmentar antes (R5)");
        Pacote p = new Pacote();
        p.seqNum   = seq;
        p.ackNum   = 0;
        p.flags    = RdtConstants.FLAG_DATA
                   | (ultimoFragmentoDaMensagem ? RdtConstants.FLAG_FIN : 0);
        p.checksum = 0;                          // OBRIGATORIO zerar antes
        p.dataLen  = dados.length;
        p.data     = dados.clone();
        p.checksum = checksumInternet(serializar(p));
        return p;
    }

    /** Cria um ACK cumulativo confirmando o ultimo pacote recebido EM ORDEM. */
    public static Pacote criarAck(int seqRecebido) {
        if (seqRecebido < 0 || seqRecebido >= RdtConstants.SEQ_MOD)
            throw new IllegalArgumentException("ack_num fora de 0..255");
        Pacote a = new Pacote();
        a.seqNum   = 0;
        a.ackNum   = seqRecebido;
        a.flags    = RdtConstants.FLAG_ACK;
        a.checksum = 0;
        a.dataLen  = 0;
        a.data     = new byte[0];
        a.checksum = checksumInternet(serializar(a));
        return a;
    }

    /** Resultado de validarAck — espelha VALIDAR_ACK da Secao 4. */
    public static final int ACK_ER      = -1;   // malformado: log ER e descartar
    public static final int ACK_CE      = -2;   // checksum invalido: log CE e descartar
    public static final int ACK_NAO_ACK = -3;   // valido, mas nao e ACK: ignorar

    /**
     * Validacao de ACK em A (Secao 4), em duas etapas.
     * Retorna ack_num (0..255) se valido, ou ACK_ER / ACK_CE / ACK_NAO_ACK.
     */
    public static int validarAck(byte[] buf) {
        Pacote ack;
        try {
            ack = desserializar(buf);
        } catch (FormatoInvalidoException e) {
            return ACK_ER;
        }
        if (!checksumOk(buf, ack)) return ACK_CE;
        if (ack.flags != RdtConstants.FLAG_ACK) return ACK_NAO_ACK;
        return ack.ackNum;
    }

    // ------------------------------------------------------------------------
    // ARITMETICA MODULAR DA JANELA (Secao 7.1)
    // ------------------------------------------------------------------------

    /**
     * Quantos passos de b ate a, no circulo 0..255. Math.floorMod garante
     * resultado nao-negativo (em Java, % de negativo pode ser negativo).
     */
    public static int dist(int a, int b) {
        return Math.floorMod(a - b, RdtConstants.SEQ_MOD);
    }

    /** Proximo numero de sequencia (com wrap-around 255 -> 0). */
    public static int prox(int s) {
        return (s + 1) % RdtConstants.SEQ_MOD;
    }

    /**
     * True se o ACK confirma algo dentro da janela pendente do remetente.
     * NUNCA comparar numeros de sequencia com <, > ou >= diretamente.
     */
    public static boolean ackValido(int numAck, int sendBase, int nextSeqNum) {
        return dist(numAck, sendBase) < dist(nextSeqNum, sendBase);
    }

    // ------------------------------------------------------------------------
    // FRAGMENTACAO DE MENSAGENS (Regra R5 + Secao 3.3)
    // ------------------------------------------------------------------------

    /** Fragmento de mensagem: bloco de ate MAX_PAYLOAD bytes + marcador de ultimo. */
    public static class Fragmento {
        public final byte[] dados;
        public final boolean ultimo;   // passar a criarPacote (marca o FIN = 0x90)
        public Fragmento(byte[] dados, boolean ultimo) {
            this.dados = dados;
            this.ultimo = ultimo;
        }
    }

    /**
     * Divide a mensagem em fragmentos de ate MAX_PAYLOAD bytes. O campo
     * 'ultimo' do ultimo fragmento deve ser passado a criarPacote para marcar
     * o FIN (0x90), permitindo a remontagem em C (Secao 3.3).
     */
    public static List<Fragmento> fragmentarMensagem(byte[] dados) {
        List<Fragmento> frags = new ArrayList<>();
        if (dados.length == 0) {
            frags.add(new Fragmento(new byte[0], true));
            return frags;
        }
        int max = RdtConstants.MAX_PAYLOAD;
        for (int i = 0; i < dados.length; i += max) {
            int fim = Math.min(i + max, dados.length);
            frags.add(new Fragmento(Arrays.copyOfRange(dados, i, fim),
                                    fim == dados.length));
        }
        return frags;
    }
}

