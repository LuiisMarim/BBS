/**
 * Módulo de Mensagens
 * Funções auxiliares para criação e serialização de mensagens com MessagePack
 */

const msgpack = require('msgpack-lite');

/**
 * Cria uma mensagem serializada com MessagePack
 * @param {string} service - Nome do serviço
 * @param {Object} data - Dados da mensagem
 * @param {LogicalClock} logicalClock - Instância do relógio lógico
 * @returns {Buffer} Mensagem serializada
 */
function createMessage(service, data, logicalClock) {
  // Incrementa o relógio antes de enviar
  const clockValue = logicalClock.increment();
  
  // Adiciona timestamp e clock aos dados
  data.timestamp = Date.now() / 1000;
  data.clock = clockValue;
  
  const message = {
    service: service,
    data: data
  };
  
  return msgpack.encode(message);
}

/**
 * Deserializa uma mensagem MessagePack
 * @param {Buffer} rawMessage - Mensagem em bytes
 * @returns {Object} Objeto com a mensagem deserializada
 */
function parseMessage(rawMessage) {
  try {
    return msgpack.decode(rawMessage);
  } catch (error) {
    console.error('Erro ao deserializar mensagem:', error);
    return {};
  }
}

/**
 * Cria uma mensagem de resposta
 * @param {string} service - Nome do serviço
 * @param {string} status - Status da resposta ('sucesso' ou 'erro')
 * @param {Object} data - Dados adicionais da resposta
 * @param {LogicalClock} logicalClock - Instância do relógio lógico
 * @param {string} description - Descrição de erro opcional (conforme especificação Parte 1)
 * @returns {Buffer} Resposta serializada
 */
function createResponse(service, status, data, logicalClock, description = null) {
  const clockValue = logicalClock.increment();
  
  const responseData = {
    status: status,
    timestamp: Date.now() / 1000,
    clock: clockValue,
    ...data
  };
  
  if (description) {
    responseData.description = description;
  }
  
  const response = {
    service: service,
    data: responseData
  };
  
  return msgpack.encode(response);
}

/**
 * Atualiza o relógio lógico com base no valor recebido
 * @param {LogicalClock} logicalClock - Instância do relógio lógico
 * @param {number} receivedClock - Valor do relógio recebido
 */
function updateLogicalClock(logicalClock, receivedClock) {
  logicalClock.update(receivedClock);
}

module.exports = {
  createMessage,
  parseMessage,
  createResponse,
  updateLogicalClock
};
