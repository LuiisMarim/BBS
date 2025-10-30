/**
 * Utilitários comuns para o sistema BBS em JavaScript/Node.js
 */

const LogicalClock = require('./logicalClock');
const {
  createMessage,
  parseMessage,
  createResponse,
  updateLogicalClock
} = require('./messaging');

module.exports = {
  LogicalClock,
  createMessage,
  parseMessage,
  createResponse,
  updateLogicalClock
};
