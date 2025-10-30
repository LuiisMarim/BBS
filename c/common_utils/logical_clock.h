/**
 * Relógio Lógico de Lamport em C
 * Implementa o contador lógico para sincronização de eventos distribuídos
 */

#ifndef LOGICAL_CLOCK_H
#define LOGICAL_CLOCK_H

typedef struct {
    int counter;
} LogicalClock;

/**
 * Inicializa o relógio lógico
 * @param clock Ponteiro para a estrutura LogicalClock
 */
void logical_clock_init(LogicalClock *clock);

/**
 * Incrementa o contador antes de enviar uma mensagem
 * @param clock Ponteiro para a estrutura LogicalClock
 * @return Novo valor do contador
 */
int logical_clock_increment(LogicalClock *clock);

/**
 * Atualiza o relógio ao receber uma mensagem
 * @param clock Ponteiro para a estrutura LogicalClock
 * @param received_time Valor do relógio recebido na mensagem
 * @return Novo valor do contador
 */
int logical_clock_update(LogicalClock *clock, int received_time);

/**
 * Retorna o valor atual do contador sem modificá-lo
 * @param clock Ponteiro para a estrutura LogicalClock
 * @return Valor atual do contador
 */
int logical_clock_get_time(LogicalClock *clock);

#endif /* LOGICAL_CLOCK_H */
