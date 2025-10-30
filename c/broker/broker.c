/**
 * Broker - Intermediário REQ-REP usando padrão ROUTER-DEALER
 * Faz balanceamento de carga round-robin entre os servidores
 * Porta: 5555 (frontend para clientes), 5556 (backend para servidores)
 * 
 * ATUALIZAÇÃO: Agora valida MessagePack para conformidade com Parte 3
 * Mantém comportamento de roteamento transparente, mas verifica formato
 */

#include <zmq.h>
#include <msgpack.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <stdlib.h>
#include "../common_utils/logical_clock.h"

#define FRONTEND_PORT "tcp://*:5555"
#define BACKEND_PORT "tcp://*:5556"
#define MSGPACK_VALIDATION_ENABLED 1  // Ativar/desativar validação

// Flag para controlar o loop principal
static volatile int s_interrupted = 0;

/**
 * Handler para sinais de interrupção (SIGINT, SIGTERM)
 */
static void s_signal_handler(int signal_value) {
    s_interrupted = 1;
}

/**
 * Instala handlers de sinais
 */
static void s_catch_signals(void) {
    struct sigaction action;
    action.sa_handler = s_signal_handler;
    action.sa_flags = 0;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
}

/**
 * Valida se uma mensagem está em formato MessagePack válido
 * Retorna 1 se válida, 0 se inválida
 * Nota: Esta validação é um sanity check, não modifica a mensagem
 */
static int validate_msgpack(const char *data, size_t size) {
    if (!MSGPACK_VALIDATION_ENABLED) {
        return 1;  // Validação desabilitada, sempre válido
    }
    
    if (!data || size == 0) {
        return 0;
    }
    
    msgpack_unpacked msg;
    msgpack_unpacked_init(&msg);
    
    msgpack_unpack_return ret = msgpack_unpack_next(&msg, data, size, NULL);
    
    msgpack_unpacked_destroy(&msg);
    
    return (ret == MSGPACK_UNPACK_SUCCESS) ? 1 : 0;
}

/**
 * Processa e roteia mensagem com validação MessagePack
 * Mantém comportamento transparente: encaminha mesmo se inválida (com warning)
 */
static void process_message(zmq_msg_t *msg, const char *direction, unsigned long *msg_count) {
    size_t size = zmq_msg_size(msg);
    void *data = zmq_msg_data(msg);
    
    // Valida MessagePack (apenas para frames de dados, ignora identidades)
    if (size > 0 && MSGPACK_VALIDATION_ENABLED) {
        if (!validate_msgpack((const char*)data, size)) {
            fprintf(stderr, "[BROKER] WARNING: Mensagem #%lu (%s) não é MessagePack válido (%zu bytes)\n",
                    *msg_count, direction, size);
            // Continua encaminhando (comportamento tolerante a falhas)
        } else {
            if (*msg_count % 1000 == 0) {  // Log periódico
                printf("[BROKER] Mensagem #%lu (%s) validada: MessagePack OK (%zu bytes)\n",
                       *msg_count, direction, size);
            }
        }
    }
    
    (*msg_count)++;
}

/**
 * Função principal do broker
 * Conecta frontend (ROUTER) com backend (DEALER) fazendo proxy das mensagens
 */
int main(void) {
    printf("[BROKER] Iniciando broker REQ-REP...\n");
    
    // Instala handlers de sinais
    s_catch_signals();
    
    // Inicializa contexto ZeroMQ
    void *context = zmq_ctx_new();
    if (!context) {
        fprintf(stderr, "[BROKER] Erro ao criar contexto ZeroMQ\n");
        return 1;
    }
    
    // Socket ROUTER para clientes (frontend)
    void *frontend = zmq_socket(context, ZMQ_ROUTER);
    if (!frontend) {
        fprintf(stderr, "[BROKER] Erro ao criar socket frontend\n");
        zmq_ctx_destroy(context);
        return 1;
    }
    
    // Socket DEALER para servidores (backend)
    void *backend = zmq_socket(context, ZMQ_DEALER);
    if (!backend) {
        fprintf(stderr, "[BROKER] Erro ao criar socket backend\n");
        zmq_close(frontend);
        zmq_ctx_destroy(context);
        return 1;
    }
    
    // Bind nos sockets
    int rc = zmq_bind(frontend, FRONTEND_PORT);
    if (rc != 0) {
        fprintf(stderr, "[BROKER] Erro ao fazer bind no frontend: %s\n", zmq_strerror(errno));
        zmq_close(frontend);
        zmq_close(backend);
        zmq_ctx_destroy(context);
        return 1;
    }
    printf("[BROKER] Frontend (ROUTER) escutando em %s\n", FRONTEND_PORT);
    
    rc = zmq_bind(backend, BACKEND_PORT);
    if (rc != 0) {
        fprintf(stderr, "[BROKER] Erro ao fazer bind no backend: %s\n", zmq_strerror(errno));
        zmq_close(frontend);
        zmq_close(backend);
        zmq_ctx_destroy(context);
        return 1;
    }
    printf("[BROKER] Backend (DEALER) escutando em %s\n", BACKEND_PORT);
    
    // Inicializa relógio lógico
    LogicalClock clock;
    logical_clock_init(&clock);
    
    printf("[BROKER] Broker pronto para rotear mensagens\n");
    printf("[BROKER] Clientes conectam em %s\n", FRONTEND_PORT);
    printf("[BROKER] Servidores conectam em %s\n", BACKEND_PORT);
    printf("[BROKER] Validação MessagePack: %s\n", 
           MSGPACK_VALIDATION_ENABLED ? "ATIVADA" : "DESATIVADA");
    
    // Contadores de mensagens
    unsigned long frontend_msg_count = 0;
    unsigned long backend_msg_count = 0;
    
    // Proxy manual com validação MessagePack
    // Mantém comportamento equivalente a zmq_proxy() mas com inspeção
    zmq_pollitem_t items[] = {
        { frontend, 0, ZMQ_POLLIN, 0 },
        { backend, 0, ZMQ_POLLIN, 0 }
    };
    
    while (!s_interrupted) {
        // Poll com timeout de 1 segundo
        int rc = zmq_poll(items, 2, 1000);
        if (rc < 0) {
            break;  // Erro ou interrupção
        }
        
        // Mensagens do frontend (clientes) para backend (servidores)
        if (items[0].revents & ZMQ_POLLIN) {
            zmq_msg_t msg;
            while (1) {
                zmq_msg_init(&msg);
                int size = zmq_msg_recv(&msg, frontend, 0);
                if (size < 0) {
                    zmq_msg_close(&msg);
                    break;
                }
                
                // Valida MessagePack se for frame de dados
                int more = zmq_msg_more(&msg);
                if (!more && size > 0) {  // Último frame = mensagem de dados
                    process_message(&msg, "frontend->backend", &frontend_msg_count);
                }
                
                // Encaminha para backend
                zmq_msg_send(&msg, backend, more ? ZMQ_SNDMORE : 0);
                zmq_msg_close(&msg);
                
                if (!more) break;
            }
        }
        
        // Mensagens do backend (servidores) para frontend (clientes)
        if (items[1].revents & ZMQ_POLLIN) {
            zmq_msg_t msg;
            while (1) {
                zmq_msg_init(&msg);
                int size = zmq_msg_recv(&msg, backend, 0);
                if (size < 0) {
                    zmq_msg_close(&msg);
                    break;
                }
                
                // Valida MessagePack se for frame de dados
                int more = zmq_msg_more(&msg);
                if (!more && size > 0) {  // Último frame = mensagem de dados
                    process_message(&msg, "backend->frontend", &backend_msg_count);
                }
                
                // Encaminha para frontend
                zmq_msg_send(&msg, frontend, more ? ZMQ_SNDMORE : 0);
                zmq_msg_close(&msg);
                
                if (!more) break;
            }
        }
    }
    
    // Estatísticas finais
    printf("\n[BROKER] Estatísticas:\n");
    printf("[BROKER]   Mensagens frontend->backend: %lu\n", frontend_msg_count);
    printf("[BROKER]   Mensagens backend->frontend: %lu\n", backend_msg_count);
    
    // Cleanup
    printf("[BROKER] Encerrando broker...\n");
    zmq_close(frontend);
    zmq_close(backend);
    zmq_ctx_destroy(context);
    
    return 0;
}
