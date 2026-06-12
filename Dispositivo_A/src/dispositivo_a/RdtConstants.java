package dispositivo_a;

/**
 * RdtConstants.java — Constantes globais do protocolo RDT 4.0 (Grupo 3).
 * Fonte normativa: RDT4_Especificacao.pdf, Secao 11.
 * NAO alterar valores sem combinar com todo o grupo: todas as maquinas
 * (A, B e C) devem usar exatamente estes valores.
 */
public final class RdtConstants {

    private RdtConstants() {}                       // nao instanciavel

    public static final int WINDOW_SIZE  = 5;       // janela deslizante (Go-Back-N)
    public static final int SEQ_MOD      = 256;     // modulo do espaco de sequencia (uint8)
    public static final int SEQ_INICIAL  = 0;       // alteravel SO no teste I14
    public static final int HEADER_SIZE  = 7;       // bytes do cabecalho fixo
    public static final int MAX_PAYLOAD  = 1400;    // maximo de bytes de payload
    public static final int TIMEOUT_MS   = 2000;    // timeout do timer unico de A
    public static final int ATRASO_B_MS  = 3000;    // atraso aplicado pelo menu de B

    public static final int FLAG_DATA = 0x80;       // pacote de dados (fragmento intermediario)
    public static final int FLAG_ACK  = 0x40;       // ACK puro
    public static final int FLAG_FIN  = 0x10;       // ultimo fragmento da mensagem (DATA|FIN = 0x90)

    /** Unicas combinacoes de flags aceitas (Secao 3.2). */
    public static final int[] FLAGS_VALIDAS = {0x80, 0x90, 0x40};

    public static final int PORT_B_DADOS = 9000;    // B escuta dados de A
    public static final int PORT_C_DADOS = 9001;    // C escuta dados de B
    public static final int PORT_B_ACK   = 9002;    // B escuta ACKs de C
    public static final int PORT_A_ACK   = 9003;    // A escuta ACKs de B

    public static final String ENCODING = "UTF-8";  // codificacao texto <-> bytes
}

