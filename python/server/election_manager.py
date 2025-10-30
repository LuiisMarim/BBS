#!/usr/bin/env python3
"""
Módulo de Eleição de Coordenador - Algoritmo Bully
Implementa eleição distribuída entre servidores com base em rank
"""

import zmq
import time
import msgpack
from typing import List, Dict, Optional
from threading import Lock

class ElectionManager:
    """
    Gerenciador de eleição de coordenador usando algoritmo Bully
    
    O servidor com maior rank torna-se coordenador.
    Eleição é iniciada quando o coordenador atual falha.
    """
    
    def __init__(self, server_name: str, rank: int, pub_socket, datastore):
        """
        Inicializa o gerenciador de eleição
        
        Args:
            server_name: Nome deste servidor
            rank: Rank atribuído pelo ReferenceServer
            pub_socket: Socket PUB para anunciar coordenador
            datastore: Instância do DataStore para persistir logs
        """
        self.server_name = server_name
        self.rank = rank
        self.pub_socket = pub_socket
        self.datastore = datastore
        
        # Estado da eleição
        self.is_coordinator = False
        self.coordinator = None
        self.election_in_progress = False
        self.election_lock = Lock()
        
        # Lista de servidores conhecidos
        self.known_servers = []
        self.servers_lock = Lock()
        
        # Contexto ZeroMQ para comunicação REQ/REP
        self.context = zmq.Context()
        
        # Socket REP para receber requisições de eleição (porta 6001)
        self.election_socket = self.context.socket(zmq.REP)
        
        # Log de eleições
        self.election_log = []
        self.log_lock = Lock()
        
        print(f"[ELECTION:{self.server_name}] Gerenciador inicializado (rank {rank})")
    
    def start_election_server(self):
        """Inicia servidor de eleição em porta dedicada"""
        try:
            self.election_socket.bind("tcp://*:6001")
            print(f"[ELECTION:{self.server_name}] Servidor de eleição escutando na porta 6001")
            
            from threading import Thread
            thread = Thread(target=self._handle_election_requests, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"[ELECTION:{self.server_name}] Erro ao iniciar servidor de eleição: {e}")
    
    def _handle_election_requests(self):
        """Thread que processa requisições de eleição"""
        while True:
            try:
                # Recebe requisição
                raw_request = self.election_socket.recv()
                request = msgpack.unpackb(raw_request, raw=False)
                
                service = request.get('service', '')
                data = request.get('data', {})
                
                # Processa baseado no serviço
                if service == 'election':
                    response = self._handle_election_request(data)
                elif service == 'coordinator':
                    response = self._handle_coordinator_announcement(data)
                else:
                    response = {
                        'service': service,
                        'data': {'status': 'error', 'message': f'Serviço desconhecido: {service}'}
                    }
                
                # Envia resposta
                self.election_socket.send(msgpack.packb(response))
                
            except Exception as e:
                print(f"[ELECTION:{self.server_name}] Erro ao processar requisição: {e}")
                error_response = {
                    'service': 'error',
                    'data': {'status': 'error', 'message': str(e)}
                }
                self.election_socket.send(msgpack.packb(error_response))
    
    def _handle_election_request(self, data: Dict) -> Dict:
        """
        Processa requisição de eleição de outro servidor
        
        Args:
            data: Dados da requisição com rank do requisitante
        
        Returns:
            Resposta com status "OK" e rank próprio
        """
        requester_rank = data.get('rank', 0)
        requester_name = data.get('server', '')
        
        print(f"[ELECTION:{self.server_name}] Requisição de eleição recebida de {requester_name} (rank {requester_rank})")
        
        # Se meu rank é maior, respondo OK e inicio minha própria eleição
        if self.rank > requester_rank:
            print(f"[ELECTION:{self.server_name}] Meu rank ({self.rank}) é maior. Respondendo OK e iniciando eleição.")
            
            # Inicia eleição própria em thread separada (não bloqueia resposta)
            from threading import Thread
            Thread(target=self.start_election, daemon=True).start()
        
        return {
            'service': 'election',
            'data': {
                'status': 'OK',
                'rank': self.rank,
                'server': self.server_name,
                'timestamp': time.time()
            }
        }
    
    def _handle_coordinator_announcement(self, data: Dict) -> Dict:
        """
        Processa anúncio de novo coordenador
        
        Args:
            data: Dados do anúncio
        
        Returns:
            Confirmação de recebimento
        """
        new_coordinator = data.get('coordinator', '')
        coordinator_rank = data.get('rank', 0)
        
        print(f"[ELECTION:{self.server_name}] Coordenador anunciado: {new_coordinator} (rank {coordinator_rank})")
        
        with self.election_lock:
            self.coordinator = new_coordinator
            self.is_coordinator = (new_coordinator == self.server_name)
            self.election_in_progress = False
        
        # Registra no log
        self._log_election_event('coordinator_announced', new_coordinator, coordinator_rank)
        
        return {
            'service': 'coordinator',
            'data': {
                'status': 'OK',
                'timestamp': time.time()
            }
        }
    
    def update_server_list(self, server_list: List[Dict]):
        """
        Atualiza lista de servidores conhecidos
        
        Args:
            server_list: Lista de servidores [{name, rank}, ...]
        """
        with self.servers_lock:
            self.known_servers = server_list.copy()
    
    def start_election(self):
        """
        Inicia processo de eleição usando algoritmo Bully
        
        Passos:
        1. Envia ELECTION para todos os servidores com rank maior
        2. Se receber OK de algum, cancela eleição (outro assumirá)
        3. Se não receber OK, declara-se coordenador
        4. Anuncia coordenação para todos
        """
        with self.election_lock:
            if self.election_in_progress:
                print(f"[ELECTION:{self.server_name}] Eleição já em progresso, ignorando.")
                return
            
            self.election_in_progress = True
        
        print(f"[ELECTION:{self.server_name}] Iniciando eleição (rank {self.rank})")
        self._log_election_event('election_started', self.server_name, self.rank)
        
        # Encontra servidores com rank maior
        higher_rank_servers = []
        with self.servers_lock:
            for server in self.known_servers:
                if server['rank'] > self.rank and server['name'] != self.server_name:
                    higher_rank_servers.append(server)
        
        # Se não há servidores com rank maior, sou o coordenador
        if not higher_rank_servers:
            print(f"[ELECTION:{self.server_name}] Nenhum servidor com rank maior. Tornando-me coordenador.")
            self._become_coordinator()
            return
        
        # Envia requisição ELECTION para servidores com rank maior
        received_ok = False
        for server in higher_rank_servers:
            try:
                socket = self.context.socket(zmq.REQ)
                socket.setsockopt(zmq.RCVTIMEO, 2000)  # Timeout 2s
                socket.setsockopt(zmq.SNDTIMEO, 2000)
                
                address = f"tcp://{server['name']}:6001"
                socket.connect(address)
                
                # Envia requisição de eleição
                request = msgpack.packb({
                    'service': 'election',
                    'data': {
                        'rank': self.rank,
                        'server': self.server_name,
                        'timestamp': time.time()
                    }
                })
                
                socket.send(request)
                
                # Aguarda resposta
                raw_response = socket.recv()
                response = msgpack.unpackb(raw_response, raw=False)
                
                if response.get('data', {}).get('status') == 'OK':
                    print(f"[ELECTION:{self.server_name}] Recebido OK de {server['name']}. Cancelando eleição.")
                    received_ok = True
                
                socket.close()
                
            except Exception as e:
                print(f"[ELECTION:{self.server_name}] Erro ao contactar {server['name']}: {e}")
                continue
        
        # Se não recebeu OK de ninguém, torna-se coordenador
        if not received_ok:
            print(f"[ELECTION:{self.server_name}] Nenhum OK recebido. Tornando-me coordenador.")
            self._become_coordinator()
        else:
            # Outro servidor de rank maior assumirá
            with self.election_lock:
                self.election_in_progress = False
            print(f"[ELECTION:{self.server_name}] Aguardando anúncio do novo coordenador.")
    
    def _become_coordinator(self):
        """Declara-se coordenador e anuncia para todos"""
        with self.election_lock:
            self.is_coordinator = True
            self.coordinator = self.server_name
            self.election_in_progress = False
        
        print(f"[ELECTION:{self.server_name}] Sou o novo COORDENADOR (rank {self.rank})")
        self._log_election_event('became_coordinator', self.server_name, self.rank)
        
        # Anuncia no tópico 'servers' via PUB-SUB
        self._publish_coordinator_announcement()
        
        # Envia anúncio direto via REQ/REP para cada servidor
        self._announce_to_all_servers()
    
    def _publish_coordinator_announcement(self):
        """Publica anúncio de coordenador no tópico 'servers'"""
        try:
            announcement = {
                'service': 'election',
                'data': {
                    'event': 'new_coordinator',
                    'coordinator': self.server_name,
                    'rank': self.rank,
                    'timestamp': time.time()
                }
            }
            
            message = msgpack.packb(announcement)
            self.pub_socket.send_multipart([b'servers', message])
            
            print(f"[ELECTION:{self.server_name}] Coordenador anunciado no tópico 'servers'")
            
        except Exception as e:
            print(f"[ELECTION:{self.server_name}] Erro ao publicar anúncio: {e}")
    
    def _announce_to_all_servers(self):
        """Envia anúncio de coordenador diretamente para todos os servidores"""
        with self.servers_lock:
            servers_to_notify = [s for s in self.known_servers if s['name'] != self.server_name]
        
        for server in servers_to_notify:
            try:
                socket = self.context.socket(zmq.REQ)
                socket.setsockopt(zmq.RCVTIMEO, 2000)
                socket.setsockopt(zmq.SNDTIMEO, 2000)
                
                address = f"tcp://{server['name']}:6001"
                socket.connect(address)
                
                announcement = msgpack.packb({
                    'service': 'coordinator',
                    'data': {
                        'coordinator': self.server_name,
                        'rank': self.rank,
                        'timestamp': time.time()
                    }
                })
                
                socket.send(announcement)
                socket.recv()  # Aguarda confirmação
                socket.close()
                
                print(f"[ELECTION:{self.server_name}] Anúncio enviado para {server['name']}")
                
            except Exception as e:
                print(f"[ELECTION:{self.server_name}] Erro ao anunciar para {server['name']}: {e}")
    
    def _log_election_event(self, event_type: str, server: str, rank: int):
        """
        Registra evento de eleição no log
        
        Args:
            event_type: Tipo do evento
            server: Nome do servidor envolvido
            rank: Rank do servidor
        """
        with self.log_lock:
            log_entry = {
                'timestamp': time.time(),
                'event': event_type,
                'server': server,
                'rank': rank,
                'local_server': self.server_name
            }
            self.election_log.append(log_entry)
            
            # Persiste log
            self.datastore.save_replication('election_log', {
                'server': self.server_name,
                'log': self.election_log
            })
    
    def check_coordinator_health(self, last_heartbeat_time: float, timeout: int = 15) -> bool:
        """
        Verifica se coordenador está saudável
        
        Args:
            last_heartbeat_time: Timestamp do último heartbeat
            timeout: Timeout em segundos
        
        Returns:
            True se saudável, False se falhou
        """
        if not self.coordinator or self.is_coordinator:
            return True
        
        current_time = time.time()
        elapsed = current_time - last_heartbeat_time
        
        if elapsed > timeout:
            print(f"[ELECTION:{self.server_name}] Coordenador {self.coordinator} falhou (timeout {elapsed:.1f}s)")
            return False
        
        return True
    
    def cleanup(self):
        """Limpeza de recursos"""
        try:
            self.election_socket.close()
        except:
            pass
