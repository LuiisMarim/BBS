#!/usr/bin/env python3
"""
Servidor de Referência
Gerencia coordenação, ranks, lista de servidores ativos e heartbeat
Porta: 5559 (REQ-REP)
"""

import zmq
import time
import sys
import os
from threading import Thread, Lock

# Adiciona o diretório common_utils ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common_utils'))

from logical_clock import LogicalClock
from persistence import DataStore
from messaging import create_message, parse_message, create_response, update_logical_clock

# Configurações
REF_PORT = "tcp://*:5559"
HEARTBEAT_TIMEOUT = 30  # segundos

class ReferenceServer:
    """Servidor de Referência para coordenação de servidores"""
    
    def __init__(self):
        """Inicializa o servidor de referência"""
        self.clock = LogicalClock()
        self.datastore = DataStore('/data')
        
        # Lista de servidores: {nome: {rank: int, last_heartbeat: float}}
        self.servers = {}
        self.server_lock = Lock()
        
        # Contador de ranks
        self.next_rank = 1
        
        # Contexto ZeroMQ
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        
        # Carrega estado anterior se existir
        self._load_state()
    
    def _load_state(self):
        """Carrega estado salvo anteriormente"""
        data = self.datastore.load('reference.json', default={})
        
        if data:
            self.servers = data.get('servers', {})
            self.next_rank = data.get('next_rank', 1)
            
            # Atualiza timestamps de heartbeat para now
            current_time = time.time()
            for server_name in self.servers:
                self.servers[server_name]['last_heartbeat'] = current_time
            
            print(f"[REFERENCE] Estado carregado: {len(self.servers)} servidores")
    
    def _save_state(self):
        """Salva estado atual"""
        data = {
            'servers': self.servers,
            'next_rank': self.next_rank,
            'timestamp': time.time()
        }
        self.datastore.save('reference.json', data)
    
    def _cleanup_inactive_servers(self):
        """Remove servidores inativos (sem heartbeat)"""
        current_time = time.time()
        inactive = []
        
        with self.server_lock:
            for name, info in self.servers.items():
                if current_time - info['last_heartbeat'] > HEARTBEAT_TIMEOUT:
                    inactive.append(name)
            
            for name in inactive:
                print(f"[REFERENCE] Removendo servidor inativo: {name}")
                del self.servers[name]
            
            if inactive:
                self._save_state()
    
    def handle_rank_request(self, data):
        """
        Atribui rank a um servidor
        
        Args:
            data: Dados da requisição com 'user' (nome do servidor)
        
        Returns:
            Resposta serializada com o rank
        """
        user = data.get('user', '')
        
        if not user:
            return create_response('rank', 'erro', {}, self.clock, 
                                 'Nome do servidor não fornecido')
        
        with self.server_lock:
            # Se o servidor já existe, retorna o rank existente
            if user in self.servers:
                rank = self.servers[user]['rank']
                self.servers[user]['last_heartbeat'] = time.time()
            else:
                # Atribui novo rank
                rank = self.next_rank
                self.servers[user] = {
                    'rank': rank,
                    'last_heartbeat': time.time()
                }
                self.next_rank += 1
                print(f"[REFERENCE] Novo servidor registrado: {user} (rank {rank})")
            
            self._save_state()
        
        return create_response('rank', 'sucesso', {'rank': rank}, self.clock)
    
    def handle_list_request(self, data):
        """
        Retorna lista de servidores ativos
        
        Returns:
            Resposta serializada com a lista de servidores
        """
        with self.server_lock:
            server_list = [
                {'name': name, 'rank': info['rank']}
                for name, info in self.servers.items()
            ]
        
        return create_response('list', 'sucesso', {'list': server_list}, self.clock)
    
    def handle_heartbeat(self, data):
        """
        Atualiza heartbeat de um servidor
        
        Args:
            data: Dados da requisição com 'user' (nome do servidor)
        
        Returns:
            Resposta de confirmação
        """
        user = data.get('user', '')
        
        if not user:
            return create_response('heartbeat', 'erro', {}, self.clock,
                                 'Nome do servidor não fornecido')
        
        with self.server_lock:
            if user in self.servers:
                self.servers[user]['last_heartbeat'] = time.time()
            else:
                # Servidor desconhecido, registra com novo rank
                rank = self.next_rank
                self.servers[user] = {
                    'rank': rank,
                    'last_heartbeat': time.time()
                }
                self.next_rank += 1
                print(f"[REFERENCE] Servidor registrado via heartbeat: {user} (rank {rank})")
        
        return create_response('heartbeat', 'sucesso', {}, self.clock)
    
    def run(self):
        """Executa o loop principal do servidor de referência"""
        print("[REFERENCE] Iniciando Servidor de Referência...")
        
        # Bind no socket
        self.socket.bind(REF_PORT)
        print(f"[REFERENCE] Escutando em {REF_PORT}")
        print(f"[REFERENCE] Servidor pronto (clock: {self.clock.get_time()})")
        
        # Thread para limpeza periódica
        cleanup_thread = Thread(target=self._periodic_cleanup, daemon=True)
        cleanup_thread.start()
        
        try:
            while True:
                # Recebe mensagem
                raw_message = self.socket.recv()
                message = parse_message(raw_message)
                
                if not message:
                    continue
                
                service = message.get('service', '')
                data = message.get('data', {})
                
                # Atualiza relógio lógico
                received_clock = data.get('clock', 0)
                update_logical_clock(self.clock, received_clock)
                
                # Processa requisição baseado no serviço
                if service == 'rank':
                    response = self.handle_rank_request(data)
                elif service == 'list':
                    response = self.handle_list_request(data)
                elif service == 'heartbeat':
                    response = self.handle_heartbeat(data)
                else:
                    response = create_response(service, 'erro', {}, self.clock,
                                             f'Serviço desconhecido: {service}')
                
                # Envia resposta
                self.socket.send(response)
                
        except KeyboardInterrupt:
            print("\n[REFERENCE] Encerrando servidor de referência...")
        finally:
            self._save_state()
            self.socket.close()
            self.context.term()
    
    def _periodic_cleanup(self):
        """Thread que limpa servidores inativos periodicamente"""
        while True:
            time.sleep(10)  # Verifica a cada 10 segundos
            self._cleanup_inactive_servers()

def main():
    """Função principal"""
    server = ReferenceServer()
    server.run()

if __name__ == '__main__':
    main()
