/**
 * Relógio Lógico de Lamport
 * Implementa o contador lógico para sincronização de eventos distribuídos
 */

class LogicalClock {
  /**
   * Inicializa o relógio lógico com contador em 0
   */
  constructor() {
    this.counter = 0;
  }

  /**
   * Incrementa o contador antes de enviar uma mensagem
   * @returns {number} Novo valor do contador
   */
  increment() {
    this.counter++;
    return this.counter;
  }

  /**
   * Atualiza o relógio ao receber uma mensagem
   * Usa o máximo entre o contador atual e o recebido, depois incrementa
   * @param {number} receivedTime - Valor do relógio recebido na mensagem
   * @returns {number} Novo valor do contador
   */
  update(receivedTime) {
    this.counter = Math.max(this.counter, receivedTime) + 1;
    return this.counter;
  }

  /**
   * Retorna o valor atual do contador sem modificá-lo
   * @returns {number} Valor atual do contador
   */
  getTime() {
    return this.counter;
  }
}

module.exports = LogicalClock;
