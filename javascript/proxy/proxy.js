/**
 * Proxy - Roteador PUB-SUB usando padrão XSUB-XPUB
 * Conecta publicadores (servidores) com assinantes (clientes/bots)
 * Porta 5557: XSUB (backend - recebe de publicadores)
 * Porta 5558: XPUB (frontend - envia para assinantes)
 */

const zmq = require('zeromq');
const LogicalClock = require('../common_utils/logicalClock');

// Configurações
const XSUB_PORT = 'tcp://*:5557';
const XPUB_PORT = 'tcp://*:5558';

// Relógio lógico
const clock = new LogicalClock();

/**
 * Função principal do proxy
 */
async function main() {
  console.log('[PROXY] Iniciando proxy PUB-SUB...');
  
  try {
    // Socket XSUB para receber publicações dos servidores (backend)
    const xsub = new zmq.XSubscriber();
    
    // Socket XPUB para enviar publicações aos clientes/bots (frontend)
    const xpub = new zmq.XPublisher();
    
    // Bind nos sockets
    await xsub.bind(XSUB_PORT);
    console.log(`[PROXY] XSUB (backend) escutando em ${XSUB_PORT}`);
    
    await xpub.bind(XPUB_PORT);
    console.log(`[PROXY] XPUB (frontend) escutando em ${XPUB_PORT}`);
    
    console.log('[PROXY] Proxy pronto para rotear publicações');
    console.log('[PROXY] Servidores publicam em', XSUB_PORT);
    console.log('[PROXY] Clientes/Bots assinam em', XPUB_PORT);
    
    // Contador de mensagens
    let messageCount = 0;
    
    // Encaminha mensagens entre XSUB e XPUB de forma assíncrona
    const forwardFromXSubToXPub = async () => {
      for await (const msg of xsub) {
        clock.increment();
        messageCount++;
        
        if (messageCount % 100 === 0) {
          console.log(`[PROXY] ${messageCount} mensagens roteadas (clock: ${clock.getTime()})`);
        }
        
        await xpub.send(msg);
      }
    };
    
    // Encaminha assinaturas de XPUB para XSUB
    const forwardFromXPubToXSub = async () => {
      for await (const [msg] of xpub) {
        // Log de assinaturas (byte 0 = 1 indica subscribe, 0 indica unsubscribe)
        const isSubscribe = msg[0] === 1;
        const topic = msg.slice(1).toString();
        
        if (isSubscribe) {
          console.log(`[PROXY] Nova assinatura no tópico: ${topic || '(todos)'}`);
        } else {
          console.log(`[PROXY] Cancelamento de assinatura no tópico: ${topic || '(todos)'}`);
        }
        
        await xsub.send(msg);
      }
    };
    
    // Executa ambos os forwards em paralelo
    console.log('[PROXY] Pressione Ctrl+C para encerrar');
    await Promise.all([forwardFromXSubToXPub(), forwardFromXPubToXSub()]);
    
  } catch (error) {
    console.error('[PROXY] Erro ao iniciar proxy:', error);
    process.exit(1);
  }
}

// Tratamento de sinais de encerramento
process.on('SIGINT', () => {
  console.log('\n[PROXY] Encerrando proxy...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n[PROXY] Encerrando proxy...');
  process.exit(0);
});

// Inicia o proxy
main().catch(error => {
  console.error('[PROXY] Erro fatal:', error);
  process.exit(1);
});
