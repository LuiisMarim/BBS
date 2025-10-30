/**
 * Implementação do Relógio Lógico de Lamport em C
 */

#include "logical_clock.h"
#include <stdio.h>

/**
 * Inicializa o relógio lógico com contador em 0
 */
void logical_clock_init(LogicalClock *clock) {
    if (clock == NULL) {
        fprintf(stderr, "Erro: ponteiro de relógio nulo\n");
        return;
    }
    clock->counter = 0;
}

/**
 * Incrementa o contador antes de enviar uma mensagem
 */
int logical_clock_increment(LogicalClock *clock) {
    if (clock == NULL) {
        fprintf(stderr, "Erro: ponteiro de relógio nulo\n");
        return -1;
    }
    clock->counter++;
    return clock->counter;
}

/**
 * Atualiza o relógio ao receber uma mensagem
 * Usa o máximo entre o contador atual e o recebido, depois incrementa
 */
int logical_clock_update(LogicalClock *clock, int received_time) {
    if (clock == NULL) {
        fprintf(stderr, "Erro: ponteiro de relógio nulo\n");
        return -1;
    }
    
    clock->counter = (clock->counter > received_time) ? clock->counter : received_time;
    clock->counter++;
    
    return clock->counter;
}

/**
 * Retorna o valor atual do contador sem modificá-lo
 */
int logical_clock_get_time(LogicalClock *clock) {
    if (clock == NULL) {
        fprintf(stderr, "Erro: ponteiro de relógio nulo\n");
        return -1;
    }
    return clock->counter;
}
