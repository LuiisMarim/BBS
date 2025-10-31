/**
 * Cliente BBS
 * Interface interativa para o usuário se comunicar com o sistema
 * Conecta ao broker (5555) e ao proxy (5558)
 */

const zmq = require('zeromq');
const readline = require('readline');
const { LogicalClock, createMessage, parseMessage, updateLogicalClock } = require('../common_utils');

// Configurações
const BROKER_FRONTEND = 'tcp://broker:5555';
const PROXY_FRONTEND = 'tcp://proxy:5558';

class BBSClient {
  /**
   * Inicializa o cliente BBS
   */
  constructor() {
    this.clock = new LogicalClock();
    this.username = null;
    this.subscribedChannels = new Set();
    
    // Sockets ZeroMQ
    this.reqSocket = new zmq.Request();
    this.subSocket = new zmq.Subscriber();
    
    // Interface readline
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });
    
    // Flag para controlar listener de mensagens
    this.listeningMessages = false;
    
    console.log('[CLIENT] Cliente BBS inicializado');
  }

  /**
   * Conecta aos serviços
   */
  async connect() {
    try {
      // Conecta ao broker para requisições
      this.reqSocket.connect(BROKER_FRONTEND);
      console.log(`[CLIENT] Conectado ao broker em ${BROKER_FRONTEND}`);
      
      // Conecta ao proxy para assinaturas
      this.subSocket.connect(PROXY_FRONTEND);
      console.log(`[CLIENT] Conectado ao proxy em ${PROXY_FRONTEND}`);
      
      // Inicia listener para mensagens recebidas em background
      this.startMessageListener();
      
      return true;
    } catch (error) {
      console.error('[CLIENT] Erro ao conectar:', error);
      return false;
    }
  }

  /**
   * Inicia listener de mensagens em background
   */
  startMessageListener() {
    if (this.listeningMessages) return;
    
    this.listeningMessages = true;
    
    (async () => {
      try {
        for await (const [topic, message] of this.subSocket) {
          this.handleReceivedMessage(topic, message);
        }
      } catch (error) {
        if (this.listeningMessages) {
          console.error('[CLIENT] Erro no listener de mensagens:', error);
        }
      }
    })();
  }

  /**
   * Realiza login do usuário
   */
  async login(username) {
    try {
      const data = { user: username };
      const message = createMessage('login', data, this.clock);
      
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.status === 'sucesso') {
          this.username = username;
          
          // Assina seu próprio tópico para receber mensagens privadas
          this.subSocket.subscribe(username);
          console.log(`[CLIENT] Login realizado com sucesso: ${username}`);
          return true;
        } else {
          console.log(`[CLIENT] Erro no login: ${response.data.description || 'Erro desconhecido'}`);
          return false;
        }
      }
      
      return false;
    } catch (error) {
      console.error('[CLIENT] Erro ao fazer login:', error);
      return false;
    }
  }

  /**
   * Lista usuários cadastrados
   */
  async listUsers() {
    try {
      const message = createMessage('users', {}, this.clock);
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.users) {
          console.log('\n=== Usuários Cadastrados ===');
          response.data.users.forEach(user => console.log(`  - ${user}`));
          console.log('============================\n');
        }
      }
    } catch (error) {
      console.error('[CLIENT] Erro ao listar usuários:', error);
    }
  }

  /**
   * Cria um novo canal
   */
  async createChannel(channelName) {
    try {
      const data = { channel: channelName };
      const message = createMessage('channel', data, this.clock);
      
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.status === 'sucesso') {
          console.log(`[CLIENT] Canal #${channelName} criado com sucesso`);
          return true;
        } else {
          console.log(`[CLIENT] Erro ao criar canal: ${response.data.description || 'Erro desconhecido'}`);
          return false;
        }
      }
      
      return false;
    } catch (error) {
      console.error('[CLIENT] Erro ao criar canal:', error);
      return false;
    }
  }

  /**
   * Lista canais disponíveis
   */
  async listChannels() {
    try {
      const message = createMessage('channels', {}, this.clock);
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.channels) {
          console.log('\n=== Canais Disponíveis ===');
          response.data.channels.forEach(channel => {
            const subscribed = this.subscribedChannels.has(channel) ? ' [inscrito]' : '';
            console.log(`  - #${channel}${subscribed}`);
          });
          console.log('==========================\n');
        }
      }
    } catch (error) {
      console.error('[CLIENT] Erro ao listar canais:', error);
    }
  }

  /**
   * Inscreve-se em um canal
   */
  subscribeChannel(channelName) {
    this.subSocket.subscribe(channelName);
    this.subscribedChannels.add(channelName);
    console.log(`[CLIENT] Inscrito no canal #${channelName}`);
  }

  /**
   * Cancela inscrição em um canal
   */
  unsubscribeChannel(channelName) {
    this.subSocket.unsubscribe(channelName);
    this.subscribedChannels.delete(channelName);
    console.log(`[CLIENT] Inscrição cancelada no canal #${channelName}`);
  }

  /**
   * Publica mensagem em um canal
   */
  async publishMessage(channelName, messageText) {
    try {
      const data = {
        user: this.username,
        channel: channelName,
        message: messageText
      };
      const message = createMessage('publish', data, this.clock);
      
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.status === 'OK') {
          console.log(`[CLIENT] Mensagem publicada em #${channelName}`);
          return true;
        } else {
          console.log(`[CLIENT] Erro ao publicar: ${response.data.description || 'Erro desconhecido'}`);
          return false;
        }
      }
      
      return false;
    } catch (error) {
      console.error('[CLIENT] Erro ao publicar mensagem:', error);
      return false;
    }
  }

  /**
   * Envia mensagem privada para um usuário
   */
  async sendPrivateMessage(dstUser, messageText) {
    try {
      const data = {
        src: this.username,
        dst: dstUser,
        message: messageText
      };
      const message = createMessage('message', data, this.clock);
      
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.status === 'OK') {
          console.log(`[CLIENT] Mensagem enviada para @${dstUser}`);
          return true;
        } else {
          console.log(`[CLIENT] Erro ao enviar mensagem: ${response.data.description || 'Erro desconhecido'}`);
          return false;
        }
      }
      
      return false;
    } catch (error) {
      console.error('[CLIENT] Erro ao enviar mensagem privada:', error);
      return false;
    }
  }

  /**
   * Trata mensagens recebidas via PUB-SUB
   */
  handleReceivedMessage(topic, rawMessage) {
    try {
      const topicStr = topic.toString();
      const message = parseMessage(rawMessage);
      
      if (!message || !message.data) {
        return;
      }
      
      updateLogicalClock(this.clock, message.data.clock);
      
      const service = message.service;
      const data = message.data;
      
      if (service === 'publish') {
        // Mensagem pública em canal
        console.log(`\n[#${topicStr}] ${data.user}: ${data.message}`);
      } else if (service === 'message') {
        // Mensagem privada
        console.log(`\n[@${data.src} → você]: ${data.message}`);
      }
      
      // Reexibe o prompt
      this.rl.prompt();
      
    } catch (error) {
      console.error('[CLIENT] Erro ao processar mensagem recebida:', error);
    }
  }

  /**
   * Solicita histórico de mensagens de um canal
   */
  async getHistory(channelName, limit = 50) {
    try {
      const data = { channel: channelName, limit: limit };
      const message = createMessage('get_history', data, this.clock);
      
      await this.reqSocket.send(message);
      
      const [rawResponse] = await this.reqSocket.receive();
      const response = parseMessage(rawResponse);
      
      if (response && response.data) {
        updateLogicalClock(this.clock, response.data.clock);
        
        if (response.data.status === 'sucesso') {
          const messages = response.data.messages || [];
          console.log(`\n=== Histórico de #${channelName} (${messages.length} mensagens) ===`);
          
          messages.forEach((msg, idx) => {
            const timestamp = new Date(msg.timestamp * 1000).toLocaleTimeString();
            console.log(`  [${timestamp}] ${msg.user}: ${msg.message}`);
          });
          
          console.log('============================\n');
          return true;
        } else {
          console.log(`[CLIENT] Erro ao obter histórico: ${response.data.description || 'Erro desconhecido'}`);
          return false;
        }
      }
      
      return false;
    } catch (error) {
      console.error('[CLIENT] Erro ao obter histórico:', error);
      return false;
    }
  }

  /**
   * Mostra menu de ajuda
   */
  showHelp() {
    console.log('\n=== Comandos Disponíveis ===');
    console.log('  /help                      - Mostra esta ajuda');
    console.log('  /users                     - Lista usuários cadastrados');
    console.log('  /channels                  - Lista canais disponíveis');
    console.log('  /create <canal>            - Cria um novo canal');
    console.log('  /join <canal>              - Inscreve-se em um canal');
    console.log('  /leave <canal>             - Cancela inscrição em um canal');
    console.log('  /msg <usuário> <texto>     - Envia mensagem privada');
    console.log('  /pub <canal> <texto>       - Publica mensagem em canal');
    console.log('  /history <canal> [limite]  - Mostra histórico do canal');
    console.log('  /quit                      - Sai do cliente');
    console.log('============================\n');
  }

  /**
   * Processa comando do usuário
   */
  async processCommand(input) {
    const parts = input.trim().split(' ');
    const command = parts[0];
    
    switch (command) {
      case '/help':
        this.showHelp();
        break;
        
      case '/users':
        await this.listUsers();
        break;
        
      case '/channels':
        await this.listChannels();
        break;
        
      case '/create':
        if (parts.length < 2) {
          console.log('[CLIENT] Uso: /create <nome_do_canal>');
        } else {
          await this.createChannel(parts[1]);
        }
        break;
        
      case '/join':
        if (parts.length < 2) {
          console.log('[CLIENT] Uso: /join <nome_do_canal>');
        } else {
          this.subscribeChannel(parts[1]);
        }
        break;
        
      case '/leave':
        if (parts.length < 2) {
          console.log('[CLIENT] Uso: /leave <nome_do_canal>');
        } else {
          this.unsubscribeChannel(parts[1]);
        }
        break;
        
      case '/msg':
        if (parts.length < 3) {
          console.log('[CLIENT] Uso: /msg <usuário> <mensagem>');
        } else {
          const dstUser = parts[1];
          const messageText = parts.slice(2).join(' ');
          await this.sendPrivateMessage(dstUser, messageText);
        }
        break;
        
      case '/pub':
        if (parts.length < 3) {
          console.log('[CLIENT] Uso: /pub <canal> <mensagem>');
        } else {
          const channel = parts[1];
          const messageText = parts.slice(2).join(' ');
          await this.publishMessage(channel, messageText);
        }
        break;
      
      case '/history':
        if (parts.length < 2) {
          console.log('[CLIENT] Uso: /history <canal> [limite]');
        } else {
          const channel = parts[1];
          const limit = parts.length > 2 ? parseInt(parts[2]) : 50;
          await this.getHistory(channel, limit);
        }
        break;
        
      case '/quit':
        console.log('[CLIENT] Encerrando cliente...');
        process.exit(0);
        break;
        
      default:
        console.log(`[CLIENT] Comando desconhecido: ${command}`);
        console.log('[CLIENT] Digite /help para ver os comandos disponíveis');
    }
  }

  /**
   * Inicia interface interativa
   */
  async startInteractive() {
    console.log('\n=== Cliente BBS ===\n');
    
    // Solicita nome de usuário
    const username = await new Promise((resolve) => {
      this.rl.question('Digite seu nome de usuário: ', resolve);
    });
    
    // Faz login
    const loginSuccess = await this.login(username.trim());
    
    if (!loginSuccess) {
      console.log('[CLIENT] Falha no login. Encerrando...');
      process.exit(1);
    }
    
    this.showHelp();
    
    // Loop de comandos
    this.rl.setPrompt(`${this.username}> `);
    this.rl.prompt();
    
    this.rl.on('line', async (line) => {
      const input = line.trim();
      
      if (input) {
        await this.processCommand(input);
      }
      
      this.rl.prompt();
    });
  }

  /**
   * Inicia o cliente
   */
  async run() {
    const connected = await this.connect();
    
    if (!connected) {
      console.log('[CLIENT] Falha ao conectar. Encerrando...');
      process.exit(1);
    }
    
    await this.startInteractive();
  }
}

// Função principal
async function main() {
  const client = new BBSClient();
  await client.run();
}

// Tratamento de sinais
process.on('SIGINT', () => {
  console.log('\n[CLIENT] Encerrando cliente...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n[CLIENT] Encerrando cliente...');
  process.exit(0);
});

// Inicia o cliente
main().catch(error => {
  console.error('[CLIENT] Erro fatal:', error);
  process.exit(1);
});
