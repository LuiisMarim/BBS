#!/usr/bin/env python3
"""
Módulo de Gerenciamento de Replicação
Gerencia sincronização de dados entre servidores distribuídos
"""

import zmq
import time
import msgpack
from typing import Dict, List, Any
from threading import Thread, Lock

class ReplicationManager:
    """
    Gerenciador de replicação de dados entre servidores
    
    Implementa replicação ativa: cada servidor pode atualizar outros
    diretamente quando processar uma operação.
    """
    
    def __init__(self, server_name: str, rank: int, datastore):
        """
        Inicializa o gerenciador de replicação
        
        Args:
            server_name: Nome deste servidor
            rank: Rank atribuído pelo ReferenceServer
            datastore: Instância do DataStore para persistência
        """
        self.server_name = server_name
        self.rank = rank
        self.datastore = datastore
        
        # Lista de servidores conhecidos
        self.known_servers = []
        self.servers_lock = Lock()
        
        # Contexto ZeroMQ
        self.context = zmq.Context()
        
        # Socket REP para receber requisições de replicação (porta 6000)
        self.rep_socket = self.context.socket(zmq.REP)
        
        # Histórico de replicação
        self.replication_log = []
        self.log_lock = Lock()
        
        print(f"[REPLICATION:{self.server_name}] Gerenciador inicializado (rank {rank})")
    
    def start_replication_server(self):
        """Inicia servidor de replicação em thread separada"""
        try:
            self.rep_socket.bind("tcp://*:6000")
            print(f"[REPLICATION:{self.server_name}] Servidor de replicação escutando na porta 6000")
            
            # Thread para processar requisições
            thread = Thread(target=self._handle_replication_requests, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao iniciar servidor de replicação: {e}")
    
    def _handle_replication_requests(self):
        """Thread que processa requisições de replicação"""
        while True:
            try:
                # Recebe requisição
                raw_request = self.rep_socket.recv()
                request = msgpack.unpackb(raw_request, raw=False)
                
                service = request.get('service', '')
                data = request.get('data', {})
                
                # Processa baseado no serviço
                if service == 'replicate':
                    response = self._handle_replicate(data)
                elif service == 'get_time':
                    response = self._handle_get_time(data)
                elif service == 'apply_offset':
                    response = self._handle_apply_offset(data)
                elif service == 'sync_state':
                    response = self._handle_sync_state(data)
                else:
                    response = {
                        'service': service,
                        'data': {'status': 'error', 'message': f'Serviço desconhecido: {service}'}
                    }
                
                # Envia resposta
                self.rep_socket.send(msgpack.packb(response))
                
            except Exception as e:
                print(f"[REPLICATION:{self.server_name}] Erro ao processar requisição: {e}")
                error_response = {
                    'service': 'error',
                    'data': {'status': 'error', 'message': str(e)}
                }
                self.rep_socket.send(msgpack.packb(error_response))
    
    def _handle_replicate(self, data: Dict) -> Dict:
        """
        Processa requisição de replicação de dados
        
        Args:
            data: Dados da requisição
        
        Returns:
            Resposta com status
        """
        source_server = data.get('source_server', '')
        data_type = data.get('type', '')
        payload = data.get('payload', [])
        
        print(f"[REPLICATION:{self.server_name}] Recebendo replicação de {source_server} (tipo: {data_type})")
        
        try:
            # Mescla dados replicados com dados locais
            if data_type == 'logins':
                self._merge_logins(payload)
            elif data_type == 'channels':
                self._merge_channels(payload)
            elif data_type == 'messages':
                self._merge_messages(payload)
            else:
                return {
                    'service': 'replicate',
                    'data': {'status': 'error', 'message': f'Tipo desconhecido: {data_type}'}
                }
            
            # Registra no log
            with self.log_lock:
                log_entry = {
                    'timestamp': time.time(),
                    'source': source_server,
                    'type': data_type,
                    'records': len(payload) if isinstance(payload, list) else 1
                }
                self.replication_log.append(log_entry)
                
                # Salva log de replicação
                self.datastore.save_replication(self.server_name, {
                    'server': self.server_name,
                    'log': self.replication_log
                })
            
            print(f"[REPLICATION:{self.server_name}] Dados replicados com sucesso ({len(payload) if isinstance(payload, list) else 1} registros)")
            
            return {
                'service': 'replicate',
                'data': {'status': 'success', 'records_received': len(payload) if isinstance(payload, list) else 1}
            }
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao replicar dados: {e}")
            return {
                'service': 'replicate',
                'data': {'status': 'error', 'message': str(e)}
            }
    
    def _handle_get_time(self, data: Dict) -> Dict:
        """Retorna timestamp local (para sincronização Berkeley)"""
        return {
            'service': 'get_time',
            'data': {
                'time': time.time(),
                'server': self.server_name
            }
        }
    
    def _handle_apply_offset(self, data: Dict) -> Dict:
        """Aplica offset de sincronização Berkeley"""
        offset = data.get('offset', 0.0)
        coordinator = data.get('coordinator', '')
        
        # Nota: O offset seria aplicado ao relógio, mas como usamos time.time()
        # do sistema, apenas registramos para fins de logging
        print(f"[REPLICATION:{self.server_name}] Offset recebido de {coordinator}: {offset:.6f}s")
        
        return {
            'service': 'apply_offset',
            'data': {'status': 'success'}
        }
    
    def _handle_sync_state(self, data: Dict) -> Dict:
        """Retorna estado completo para sincronização"""
        try:
            logins = self.datastore.load('logins.json', default=[])
            channels = self.datastore.load('channels.json', default=[])
            messages = self.datastore.load('messages.json', default=[])
            
            return {
                'service': 'sync_state',
                'data': {
                    'status': 'success',
                    'state': {
                        'logins': logins,
                        'channels': channels,
                        'messages': messages
                    }
                }
            }
        except Exception as e:
            return {
                'service': 'sync_state',
                'data': {'status': 'error', 'message': str(e)}
            }
    
    def _merge_logins(self, new_logins: List[Dict]):
        """
        Mescla logins replicados com logins locais
        Remove duplicatas baseado no campo 'user'
        """
        try:
            # Carrega logins existentes
            existing = self.datastore.load('logins.json', default=[])
            
            # Cria conjunto de usuários já existentes
            existing_users = {login['user'] for login in existing if 'user' in login}
            
            # Adiciona apenas novos usuários
            for login in new_logins:
                if 'user' in login and login['user'] not in existing_users:
                    existing.append(login)
                    existing_users.add(login['user'])
            
            # Salva resultado mesclado
            self.datastore.save('logins.json', existing)
            print(f"[REPLICATION:{self.server_name}] Logins mesclados: {len(existing)} total")
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao mesclar logins: {e}")
    
    def _merge_channels(self, new_channels: List[Dict]):
        """
        Mescla canais replicados com canais locais
        Remove duplicatas baseado no campo 'channel'
        """
        try:
            # Carrega canais existentes
            existing = self.datastore.load('channels.json', default=[])
            
            # Cria conjunto de canais já existentes
            existing_channels = {ch['channel'] for ch in existing if 'channel' in ch}
            
            # Adiciona apenas novos canais
            for channel in new_channels:
                if 'channel' in channel and channel['channel'] not in existing_channels:
                    existing.append(channel)
                    existing_channels.add(channel['channel'])
            
            # Salva resultado mesclado
            self.datastore.save('channels.json', existing)
            print(f"[REPLICATION:{self.server_name}] Canais mesclados: {len(existing)} total")
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao mesclar canais: {e}")
    
    def _merge_messages(self, new_messages: List[Dict]):
        """
        Mescla mensagens replicadas com mensagens locais
        Remove duplicatas baseado em (timestamp, clock, user, channel/dst)
        Mantém ordem por timestamp e clock
        """
        try:
            # Carrega mensagens existentes
            existing = self.datastore.load('messages.json', default=[])
            
            # Cria conjunto de identificadores únicos das mensagens existentes
            existing_ids = set()
            for msg in existing:
                msg_id = self._get_message_id(msg)
                existing_ids.add(msg_id)
            
            # Adiciona apenas mensagens novas
            added = 0
            for msg in new_messages:
                msg_id = self._get_message_id(msg)
                if msg_id not in existing_ids:
                    existing.append(msg)
                    existing_ids.add(msg_id)
                    added += 1
            
            # Ordena por timestamp e clock para manter consistência
            existing.sort(key=lambda m: (m.get('timestamp', 0), m.get('clock', 0)))
            
            # Salva resultado mesclado
            self.datastore.save('messages.json', existing)
            print(f"[REPLICATION:{self.server_name}] Mensagens mescladas: {added} novas, {len(existing)} total")
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao mesclar mensagens: {e}")
    
    def _get_message_id(self, msg: Dict) -> tuple:
        """
        Gera identificador único para uma mensagem
        Baseado em: timestamp, clock, tipo, usuário e canal/destinatário
        """
        msg_type = msg.get('type', '')
        timestamp = msg.get('timestamp', 0)
        clock = msg.get('clock', 0)
        user = msg.get('user', msg.get('src', ''))
        
        if msg_type == 'publish':
            target = msg.get('channel', '')
        else:  # message (privada)
            target = msg.get('dst', '')
        
        message_text = msg.get('message', '')
        
        return (timestamp, clock, msg_type, user, target, message_text)
    
    def update_server_list(self, servers: List[Dict]):
        """
        Atualiza lista de servidores conhecidos
        
        Args:
            servers: Lista com [{name, rank}, ...]
        """
        with self.servers_lock:
            self.known_servers = [s for s in servers if s['name'] != self.server_name]
        
        print(f"[REPLICATION:{self.server_name}] Lista de servidores atualizada: {len(self.known_servers)} servidores")
    
    def replicate_to_all(self, data_type: str, payload: Any):
        """
        Replica dados para todos os servidores conhecidos
        
        Args:
            data_type: Tipo de dados ('logins', 'channels', 'messages')
            payload: Dados a replicar
        """
        with self.servers_lock:
            servers = list(self.known_servers)
        
        if not servers:
            print(f"[REPLICATION:{self.server_name}] Nenhum servidor para replicar")
            return
        
        print(f"[REPLICATION:{self.server_name}] Replicando {data_type} para {len(servers)} servidores")
        
        for server in servers:
            self._replicate_to_server(server['name'], data_type, payload)
    
    def _replicate_to_server(self, target_server: str, data_type: str, payload: Any):
        """
        Replica dados para um servidor específico
        
        Args:
            target_server: Nome do servidor destino
            data_type: Tipo de dados
            payload: Dados a replicar
        """
        try:
            socket = self.context.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, 3000)  # Timeout 3s
            socket.setsockopt(zmq.SNDTIMEO, 3000)
            
            address = f"tcp://{target_server}:6000"
            socket.connect(address)
            
            # Envia requisição de replicação
            request = msgpack.packb({
                'service': 'replicate',
                'data': {
                    'source_server': self.server_name,
                    'type': data_type,
                    'payload': payload,
                    'timestamp': time.time()
                }
            })
            
            socket.send(request)
            
            # Aguarda confirmação
            raw_response = socket.recv()
            response = msgpack.unpackb(raw_response, raw=False)
            
            if response.get('data', {}).get('status') == 'success':
                print(f"[REPLICATION:{self.server_name}] Dados replicados para {target_server}")
            else:
                print(f"[REPLICATION:{self.server_name}] Falha ao replicar para {target_server}: {response}")
            
            socket.close()
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao replicar para {target_server}: {e}")
    
    def sync_from_coordinator(self, coordinator_name: str) -> bool:
        """
        Sincroniza estado completo de um coordenador
        
        Args:
            coordinator_name: Nome do servidor coordenador
        
        Returns:
            True se sincronização foi bem-sucedida
        """
        try:
            socket = self.context.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, 5000)
            socket.setsockopt(zmq.SNDTIMEO, 5000)
            
            address = f"tcp://{coordinator_name}:6000"
            socket.connect(address)
            
            # Solicita estado completo
            request = msgpack.packb({
                'service': 'sync_state',
                'data': {'requester': self.server_name}
            })
            
            socket.send(request)
            
            # Recebe estado
            raw_response = socket.recv()
            response = msgpack.unpackb(raw_response, raw=False)
            
            if response.get('data', {}).get('status') == 'success':
                state = response['data']['state']
                
                # Aplica estado localmente
                self.datastore.save('logins.json', state.get('logins', []))
                self.datastore.save('channels.json', state.get('channels', []))
                self.datastore.save('messages.json', state.get('messages', []))
                
                print(f"[REPLICATION:{self.server_name}] Estado sincronizado de {coordinator_name}")
                socket.close()
                return True
            
            socket.close()
            return False
            
        except Exception as e:
            print(f"[REPLICATION:{self.server_name}] Erro ao sincronizar de {coordinator_name}: {e}")
            return False
    
    def get_replication_log(self) -> List[Dict]:
        """Retorna log de replicação"""
        with self.log_lock:
            return list(self.replication_log)
    
    def cleanup(self):
        """Limpa recursos"""
        self.rep_socket.close()
        self.context.term()
