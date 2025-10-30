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
    const xsub = zmq.socket('xsub');
    
    // Socket XPUB para enviar publicações aos clientes/bots (frontend)
    const xpub = zmq.socket('xpub');
    
    // Bind nos sockets
    xsub.bindSync(XSUB_PORT);
    console.log(`[PROXY] XSUB (backend) escutando em ${XSUB_PORT}`);
    
    xpub.bindSync(XPUB_PORT);
    console.log(`[PROXY] XPUB (frontend) escutando em ${XPUB_PORT}`);
    
    console.log('[PROXY] Proxy pronto para rotear publicações');
    console.log('[PROXY] Servidores publicam em', XSUB_PORT);
    console.log('[PROXY] Clientes/Bots assinam em', XPUB_PORT);
    
    // Contador de mensagens
    let messageCount = 0;
    
    // Recebe mensagens do XSUB (publicações dos servidores)
    xsub.on('message', function(topic, ...parts) {
      // Incrementa relógio lógico ao processar mensagem
      clock.increment();
      messageCount++;
      
      // Log periódico
      if (messageCount % 100 === 0) {
        console.log(`[PROXY] ${messageCount} mensagens roteadas (clock: ${clock.getTime()})`);
      }
      
      // Encaminha para XPUB (para os assinantes)
      if (parts.length > 0) {
        xpub.send([topic, ...parts]);
      } else {
        xpub.send(topic);
      }
    });
    
    // Recebe assinaturas do XPUB (clientes/bots se inscrevendo)
    xpub.on('message', function(subscription) {
      // Encaminha assinatura para XSUB
      xsub.send(subscription);
      
      // Log de assinaturas (byte 0 = 1 indica subscribe, 0 indica unsubscribe)
      const isSubscribe = subscription[0] === 1;
      const topic = subscription.slice(1).toString();
      
      if (isSubscribe) {
        console.log(`[PROXY] Nova assinatura no tópico: ${topic || '(todos)'}`);
      } else {
        console.log(`[PROXY] Cancelamento de assinatura no tópico: ${topic || '(todos)'}`);
      }
    });
    
    // Mantém o processo rodando
    console.log('[PROXY] Pressione Ctrl+C para encerrar');
    
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
