package dispositivo_a;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;

import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

/**
 * IMPLEMENTAÇÃO DA MÁQUINA A (SENDER) — PROTOCOLO RDT 4.0
 * Integrado com Interface Web via WebSocket (Porta 8080)
 */
public class MaquinaA {

    // Endereço de destino padrão (Máquina B - Simulador de rede)
    private static final String TARGET_IP = "10.13.24.55";

    // Variáveis de Estado do Go-Back-N (Modulares de 0 a 255)
    private static int sendBase = RdtConstants.SEQ_INICIAL;
    private static int nextSeqNum = RdtConstants.SEQ_INICIAL;

    // Buffer de envio indexado de 0 a 255 para retransmissões do GBN
    private static final byte[][] bufferEnvio = new byte[RdtConstants.SEQ_MOD][];

    // Sockets UDP para envio e recepção
    private static DatagramSocket socketEnvio;
    private static DatagramSocket socketAck;

    // Servidor WebSocket para a Interface Gráfica
    private static InterfaceServer servidorInterface;

    // Monitor de sincronização para controle de estado da janela e Timer único
    private static final Object lock = new Object();
    private static long timerExpiracao = 0;
    private static boolean timerAtivo = false;
    private static Thread threadTimer;

    public static void main(String[] args) {
        try {
            log("A", "INFO", "Iniciando Máquina A (Sender)...");

            // Inicialização segura do WebSocket isolada em uma thread nativa
            new Thread(() -> {
                try {
                	servidorInterface = new InterfaceServer(new java.net.InetSocketAddress("127.0.0.1", 8080));
                    servidorInterface.run(); // Usa o run direto dentro da thread isolada
                } catch (Throwable t) {
                    System.out.println("[A] [WARN] Não foi possível iniciar a interface Web (Falta SLF4J), mas o terminal UDP funcionará.");
                }
            }).start();

            log("A", "INFO", "Interface Web configurada em ws://127.0.0.1:8080");

            // Vincula o socket de escuta de ACKs à porta normatizada 9003
            socketAck = new DatagramSocket(RdtConstants.PORT_A_ACK);
            // Socket de envio associado a uma porta disponível local
            socketEnvio = new DatagramSocket();

            // 1. Inicializa a thread dedicada à recepção contínua de ACKs
            Thread threadAck = new Thread(MaquinaA::receberAcksWorker);
            threadAck.setDaemon(true);
            threadAck.start();

            // 2. Inicializa a thread responsável pelo controle de Timeout único
            threadTimer = new Thread(MaquinaA::timerWorker);
            threadTimer.setDaemon(true);
            threadTimer.start();

            // 3. Loop principal: Leitura do terminal / Digitação de mensagens
            BufferedReader teclado = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
            System.out.println("Digite as mensagens para enviar via RDT 4.0:");

            String linha;
            while ((linha = teclado.readLine()) != null) {
                if (linha.trim().isEmpty()) continue;
                processarEEnviar(linha);
            }

        } catch (Exception e) {
            log("A", "ER", "Erro fatal na execução da Máquina A: " + e.getMessage());
            e.printStackTrace();
        }
    }

    /**
     * Centraliza a lógica de fragmentação e envio (usada pelo terminal e pelo WebSocket)
     */
    private static void processarEEnviar(String mensagem) {
        try {
            byte[] dadosMensagem = mensagem.getBytes(StandardCharsets.UTF_8);
            List<RdtUtils.Fragmento> fragmentos = RdtUtils.fragmentarMensagem(dadosMensagem);

            for (RdtUtils.Fragmento frag : fragmentos) {
                enviarComJanelaGBN(frag.dados, frag.ultimo);
            }
        } catch (Exception e) {
            log("A", "ER", "Erro ao processar envio: " + e.getMessage());
        }
    }

    /**
     * Gerencia a submissão do bloco de dados à janela do Go-Back-N.
     */
    private static void enviarComJanelaGBN(byte[] bloco, boolean ehUltimoFragmento) throws Exception {
        InetAddress ipDestino = InetAddress.getByName(TARGET_IP);

        while (true) {
            synchronized (lock) {
                if (RdtUtils.dist(nextSeqNum, sendBase) < RdtConstants.WINDOW_SIZE) {
                    
                    RdtUtils.Pacote pkt = RdtUtils.criarPacote(nextSeqNum, bloco, ehUltimoFragmento);
                    byte[] bytesSerializados = RdtUtils.serializar(pkt);

                    bufferEnvio[nextSeqNum] = bytesSerializados;

                    DatagramPacket datagrama = new DatagramPacket(
                            bytesSerializados, bytesSerializados.length, ipDestino, RdtConstants.PORT_B_DADOS
                    );
                    socketEnvio.send(datagrama);

                    String conteudoTexto = new String(bloco, StandardCharsets.UTF_8);
                    log("A", "TX", String.format("SEQ=%d | FLAGS=0x%02X | LEN=%d | DATA=\"%s\"", 
                            pkt.seqNum, pkt.flags, pkt.dataLen, conteudoTexto));

                    if (sendBase == nextSeqNum) {
                        iniciarTimer();
                    }

                    nextSeqNum = RdtUtils.prox(nextSeqNum);
                    break;
                }
            }
            Thread.sleep(10);
        }
    }

    /**
     * Worker responsável por capturar datagramas de ACK de B.
     */
    private static void receberAcksWorker() {
        byte[] bufferRecv = new byte[2048];
        while (true) {
            try {
                DatagramPacket pacoteUdp = new DatagramPacket(bufferRecv, bufferRecv.length);
                socketAck.receive(pacoteUdp);

                byte[] dadosBrutos = new byte[pacoteUdp.getLength()];
                System.arraycopy(pacoteUdp.getData(), 0, dadosBrutos, 0, pacoteUdp.getLength());

                RdtUtils.Pacote ackPkt = null;
                try {
                    ackPkt = RdtUtils.desserializar(dadosBrutos);
                } catch (IllegalArgumentException e) {
                    log("A", "ER", "Datagrama malformado descartado na recepção de ACK.");
                    continue;
                }

                if (!RdtUtils.checksumOk(dadosBrutos, ackPkt)) {
                    log("A", "CE", String.format("Checksum inválido detectado no ACK. Num esperado na base: %d", sendBase));
                    continue;
                }

                if (ackPkt.flags != RdtConstants.FLAG_ACK) {
                    log("A", "ER", "Pacote recebido em 9003 não possui flag ACK.");
                    continue;
                }

                synchronized (lock) {
                    int numAck = ackPkt.ackNum;

                    if (RdtUtils.ackValido(numAck, sendBase, nextSeqNum)) {
                        sendBase = RdtUtils.prox(numAck);
                        log("A", "AK", String.format("ACK=%d | JANELA: base=%d next=%d", numAck, sendBase, nextSeqNum));

                        if (sendBase == nextSeqNum) {
                            pararTimer();
                        } else {
                            iniciarTimer();
                        }
                    }
                }

            } catch (Exception e) {
                log("A", "WARN", "Erro ao processar socket de ACK: " + e.getMessage());
            }
        }
    }

    /**
     * Gerencia a expiração temporal (Timeout único de A) em Thread paralela.
     */
    private static void timerWorker() {
        while (true) {
            try {
                Thread.sleep(10);
                synchronized (lock) {
                    if (timerAtivo && System.currentTimeMillis() >= timerExpiracao) {
                        log("A", "TO", String.format("TIMEOUT | JANELA: base=%d next=%d | Retransmitindo base ate %d", 
                                sendBase, nextSeqNum, (nextSeqNum - 1 + RdtConstants.SEQ_MOD) % RdtConstants.SEQ_MOD));
                        
                        iniciarTimer();

                        InetAddress ipDestino = InetAddress.getByName(TARGET_IP);
                        int s = sendBase;
                        while (s != nextSeqNum) {
                            byte[] pktBytes = bufferEnvio[s];
                            if (pktBytes != null) {
                                DatagramPacket dp = new DatagramPacket(
                                        pktBytes, pktBytes.length, ipDestino, RdtConstants.PORT_B_DADOS
                                );
                                socketEnvio.send(dp);
                                log("A", "RT", String.format("SEQ=%d retransmitido por Timeout", s));
                            }
                            s = RdtUtils.prox(s);
                        }
                    }
                }
            } catch (Exception e) {
                log("A", "WARN", "Erro no processador do Timer: " + e.getMessage());
            }
        }
    }

    private static void iniciarTimer() {
        timerExpiracao = System.currentTimeMillis() + RdtConstants.TIMEOUT_MS;
        timerAtivo = true;
    }

    private static void pararTimer() {
        timerAtivo = false;
    }

    /**
     * ENVIAR LOGS PARA O ECLIPSE E PARA O HTML VIA WEBSOCKET
     */
    private static void log(String dispositivo, String evento, String detalhes) {
        SimpleDateFormat sdf = new SimpleDateFormat("HH:mm:ss.SSS");
        String ts = sdf.format(new Date());
        String logFormatado = String.format("[%s] [%s] [%s] %s", ts, dispositivo, evento, detalhes);
        
        // Printa no console do Eclipse
        System.out.println(logFormatado);
        
        // Transmite em tempo real para a página web (se houver conexão ativa)
        if (servidorInterface != null) {
            servidorInterface.broadcastLog(logFormatado);
        }
    }

    /**
     * CLASSE INTERNA DO SERVIDOR WEBSOCKET (Obrigatório ser public devido ao package)
     */
    public static class InterfaceServer extends WebSocketServer {
        
        public InterfaceServer(InetSocketAddress address) {
            super(address);
        }

        @Override
        public void onOpen(WebSocket conn, ClientHandshake handshake) {}

        @Override
        public void onClose(WebSocket conn, int code, String reason, boolean remote) {}

        @Override
        public void onError(WebSocket conn, Exception ex) {}

        @Override
        public void onStart() {}

        @Override
        public void onMessage(WebSocket conn, String message) {
            // Recebe o texto digitado na interface Web e joga no fluxo de envio do RDT
            processarEEnviar(message);
        }

        public void broadcastLog(String logMessage) {
            try {
                for (WebSocket conn : getConnections()) {
                    if (conn != null && conn.isOpen()) {
                        conn.send(logMessage);
                    }
                }
            } catch (Exception e) {
                // Previne falhas de concorrência na lista de conexões
            }
        }
    }
}