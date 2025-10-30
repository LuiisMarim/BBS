#!/usr/bin/env python3
"""
Servidor de Mensagens BBS
Gerencia login, canais, mensagens, sincronização e replicação
Conecta ao broker (5556) e ao proxy (5557)
"""

import zmq
import time
import sys
import os
import random
from threading import Thread, Lock
from datetime import datetime

# Adiciona o diretório common_utils ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common_utils'))

from logical_clock import LogicalClock
from persistence import DataStore
from messaging import create_message, parse_message, create_response, update_logical_clock

# Importa módulos de sincronização, replicação e eleição
from berkeley_sync import BerkeleySynchronizer
from replication_manager import ReplicationManager
from election_manager import ElectionManager

# Configurações
BROKER_BACKEND = "tcp://broker:5556"
PROXY_BACKEND = "tcp://proxy:5557"
REFERENCE_SERVER = "tcp://reference:5559"
HEARTBEAT_INTERVAL = 10  # segundos
SYNC_INTERVAL = 10  # a cada 10 mensagens
CLOCK_SYNC_INTERVAL = 10  # a cada 10 mensagens
ELECTION_TIMEOUT = 15  # timeout para detectar falha do coordenador

class MessageServer:
    """Servidor de mensagens do sistema BBS"""
    
    def __init__(self, server_name=None):
        """
        Inicializa o servidor de mensagens
        
        Args:
            server_name: Nome do servidor (padrão: server_{random})
        """
        self.server_name = server_name or f"server_{random.randint(1000, 9999)}"
        self.clock = LogicalClock()
        self.datastore = DataStore('/data')
        
        # Estado do servidor
        self.rank = None
        self.coordinator = None
        self.message_count = 0
        self.last_coordinator_heartbeat = time.time()
        
        # Sincronização Berkeley
        self.berkeley_sync = None  # Será inicializado após obter rank
        
        # Gerenciador de replicação
        self.replication_manager = None  # Será inicializado após obter rank
        
        # Gerenciador de eleição
        self.election_manager = None  # Será inicializado após obter rank
        
        # Locks para thread-safety
        self.users_lock = Lock()
        self.channels_lock = Lock()
        self.messages_lock = Lock()
        self.coordinator_lock = Lock()
        
        # Dados locais
        self.users = set()
        self.channels = set()
        self.messages = []
        
        # Contexto ZeroMQ
        self.context = zmq.Context()
        
        # Socket REQ para broker (requisições dos clientes)
        self.req_socket = self.context.socket(zmq.REP)
        
        # Socket PUB para proxy (publicações)
        self.pub_socket = self.context.socket(zmq.PUB)
        
        # Socket REQ para servidor de referência
        self.ref_socket = self.context.socket(zmq.REQ)
        
        # Socket SUB para ouvir eleições e sincronizações
        self.sub_socket = self.context.socket(zmq.SUB)
        
        # Socket REQ para comunicação entre servidores
        self.server_socket = self.context.socket(zmq.REQ)
        
        # Carrega estado anterior
        self._load_state()
        
        print(f"[SERVER:{self.server_name}] Servidor inicializado (clock: {self.clock.get_time()})")
    
    def _load_state(self):
        """Carrega estado salvo anteriormente"""
        # Carrega logins
        logins_data = self.datastore.load('logins.json', default=[])
        self.users = set([entry['user'] for entry in logins_data if 'user' in entry])
        
        # Carrega canais
        channels_data = self.datastore.load('channels.json', default=[])
        self.channels = set([entry['channel'] for entry in channels_data if 'channel' in entry])
        
        # Carrega mensagens
        self.messages = self.datastore.load('messages.json', default=[])
        
        print(f"[SERVER:{self.server_name}] Estado carregado: {len(self.users)} usuários, "
              f"{len(self.channels)} canais, {len(self.messages)} mensagens")
    
    def _save_state(self):
        """Salva estado atual"""
        # Salva usuários
        users_data = [{'user': user, 'timestamp': time.time()} for user in self.users]
        self.datastore.save('logins.json', users_data)
        
        # Salva canais
        channels_data = [{'channel': channel, 'timestamp': time.time()} for channel in self.channels]
        self.datastore.save('channels.json', channels_data)
        
        # Salva mensagens
        self.datastore.save('messages.json', self.messages)
    
    def register_with_reference(self):
        """Registra o servidor no servidor de referência e obtém rank"""
        try:
            self.ref_socket.connect(REFERENCE_SERVER)
            
            # Solicita rank
            message = create_message('rank', {'user': self.server_name}, self.clock)
            self.ref_socket.send(message)
            
            # Recebe resposta
            raw_response = self.ref_socket.recv()
            response = parse_message(raw_response)
            
            if response:
                data = response.get('data', {})
                update_logical_clock(self.clock, data.get('clock', 0))
                
                if data.get('status') == 'sucesso':
                    self.rank = data.get('rank')
                    print(f"[SERVER:{self.server_name}] Rank atribuído: {self.rank}")
                    
                    # Inicializa sincronização Berkeley e replicação
                    self._initialize_coordination_modules()
                    
                    return True
            
            return False
            
        except Exception as e:
            print(f"[SERVER:{self.server_name}] Erro ao registrar com referência: {e}")
            return False
    
    def _initialize_coordination_modules(self):
        """Inicializa módulos de coordenação após obter rank"""
        # Inicializa gerenciador de eleição
        self.election_manager = ElectionManager(
            self.server_name, 
            self.rank, 
            self.pub_socket,
            self.datastore
        )
        self.election_manager.start_election_server()
        
        # Inicializa Berkeley (menor rank é coordenador inicial)
        is_coordinator = (self.rank == 1)
        self.berkeley_sync = BerkeleySynchronizer(self.server_name, is_coordinator, self.datastore)
        
        if is_coordinator:
            self.coordinator = self.server_name
            self.election_manager.is_coordinator = True
            self.election_manager.coordinator = self.server_name
            print(f"[SERVER:{self.server_name}] Inicializado como COORDENADOR (rank {self.rank})")
        
        # Inicializa gerenciador de replicação
        self.replication_manager = ReplicationManager(self.server_name, self.rank, self.datastore)
        self.replication_manager.start_replication_server()
        
        # Thread para atualizar lista de servidores periodicamente
        update_thread = Thread(target=self._update_server_list_periodically, daemon=True)
        update_thread.start()
        
        # Thread para monitorar coordenador
        monitor_thread = Thread(target=self._monitor_coordinator, daemon=True)
        monitor_thread.start()
    
    def send_heartbeat(self):
        """Thread que envia heartbeat periodicamente ao servidor de referência"""
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            
            try:
                message = create_message('heartbeat', {'user': self.server_name}, self.clock)
                self.ref_socket.send(message)
                
                # Recebe resposta
                raw_response = self.ref_socket.recv()
                response = parse_message(raw_response)
                
                if response:
                    data = response.get('data', {})
                    update_logical_clock(self.clock, data.get('clock', 0))
                    
            except Exception as e:
                print(f"[SERVER:{self.server_name}] Erro ao enviar heartbeat: {e}")
    
    def _update_server_list_periodically(self):
        """Thread que atualiza lista de servidores do ReferenceServer"""
        while True:
            time.sleep(20)  # Atualiza a cada 20 segundos
            
            try:
                # Solicita lista de servidores
                message = create_message('list', {}, self.clock)
                
                # Cria socket temporário para não bloquear ref_socket
                temp_socket = self.context.socket(zmq.REQ)
                temp_socket.setsockopt(zmq.RCVTIMEO, 5000)
                temp_socket.connect(REFERENCE_SERVER)
                
                temp_socket.send(message)
                raw_response = temp_socket.recv()
                response = parse_message(raw_response)
                
                if response and response.get('data', {}).get('status') == 'sucesso':
                    server_list = response['data'].get('list', [])
                    
                    # Atualiza replication manager
                    if self.replication_manager:
                        self.replication_manager.update_server_list(server_list)
                    
                    # Atualiza election manager
                    if self.election_manager:
                        self.election_manager.update_server_list(server_list)
                    
                    # Atualiza coordenador se necessário
                    self._update_coordinator_from_list(server_list)
                
                temp_socket.close()
                
            except Exception as e:
                print(f"[SERVER:{self.server_name}] Erro ao atualizar lista de servidores: {e}")
    
    def _update_coordinator_from_list(self, server_list: list):
        """Atualiza coordenador baseado na lista (menor rank)"""
        if not server_list:
            return
        
        with self.coordinator_lock:
            # Encontra servidor com menor rank
            min_rank_server = min(server_list, key=lambda s: s['rank'])
            new_coordinator = min_rank_server['name']
            
            if self.coordinator != new_coordinator:
                old_coordinator = self.coordinator
                self.coordinator = new_coordinator
                print(f"[SERVER:{self.server_name}] Coordenador mudou: {old_coordinator} -> {new_coordinator}")
                
                # Atualiza Berkeley
                if self.berkeley_sync:
                    self.berkeley_sync.is_coordinator = (new_coordinator == self.server_name)
    
    def _monitor_coordinator(self):
        """Thread que monitora saúde do coordenador e inicia eleição se necessário"""
        while True:
            time.sleep(5)
            
            with self.coordinator_lock:
                current_coordinator = self.coordinator
            
            # Se não há coordenador ou sou o coordenador, não faz nada
            if not current_coordinator or current_coordinator == self.server_name:
                self.last_coordinator_heartbeat = time.time()
                continue
            
            # Verifica se coordenador está saudável via ElectionManager
            if self.election_manager:
                is_healthy = self.election_manager.check_coordinator_health(
                    self.last_coordinator_heartbeat,
                    timeout=ELECTION_TIMEOUT
                )
                
                if not is_healthy:
                    print(f"[SERVER:{self.server_name}] Coordenador {current_coordinator} não responde. Iniciando eleição.")
                    # Inicia eleição Bully
                    Thread(target=self.election_manager.start_election, daemon=True).start()
                    # Aguarda resultado da eleição
                    time.sleep(10)
    
    def _check_sync(self):
        """Verifica se é hora de sincronizar (Berkeley e replicação)"""
        if self.message_count % SYNC_INTERVAL == 0:
            print(f"[SERVER:{self.server_name}] Sincronização necessária após {self.message_count} mensagens")
            
            # Salva estado local
            self._save_state()
            
            # Replica para outros servidores
            if self.replication_manager:
                Thread(target=self._replicate_current_state, daemon=True).start()
            
            # Sincronização Berkeley (apenas coordenador)
            if self.message_count % CLOCK_SYNC_INTERVAL == 0:
                if self.berkeley_sync and self.berkeley_sync.is_coordinator:
                    Thread(target=self._run_berkeley_sync, daemon=True).start()
    
    def _replicate_current_state(self):
        """Replica estado atual para outros servidores"""
        try:
            with self.users_lock:
                users_data = [{'user': user, 'timestamp': time.time()} for user in self.users]
            
            with self.channels_lock:
                channels_data = [{'channel': channel, 'timestamp': time.time()} for channel in self.channels]
            
            with self.messages_lock:
                messages_data = list(self.messages)
            
            # Replica cada tipo de dado
            self.replication_manager.replicate_to_all('logins', users_data)
            self.replication_manager.replicate_to_all('channels', channels_data)
            self.replication_manager.replicate_to_all('messages', messages_data)
            
            print(f"[SERVER:{self.server_name}] Estado replicado para outros servidores")
            
        except Exception as e:
            print(f"[SERVER:{self.server_name}] Erro ao replicar estado: {e}")
    
    def _run_berkeley_sync(self):
        """Executa sincronização Berkeley"""
        try:
            # Obtém lista de servidores ativos
            if not self.replication_manager:
                return
            
            server_list = [
                {'name': s['name'], 'address': f"tcp://{s['name']}:6000"}
                for s in self.replication_manager.known_servers
            ]
            
            # Adiciona a si mesmo
            server_list.append({
                'name': self.server_name,
                'address': f"tcp://{self.server_name}:6000"
            })
            
            # Executa sincronização
            success = self.berkeley_sync.run_synchronization(server_list)
            
            if success:
                # Salva histórico de sincronização
                sync_history = self.berkeley_sync.get_sync_history()
                self.datastore.save_replication('berkeley_sync', {
                    'server': self.server_name,
                    'history': sync_history
                })
            
        except Exception as e:
            print(f"[SERVER:{self.server_name}] Erro ao executar sincronização Berkeley: {e}")
    
    def handle_login(self, data):
        """Gerencia login de usuário"""
        user = data.get('user', '')
        
        if not user:
            return create_response('login', 'erro', {}, self.clock, 
                                 'Nome de usuário não fornecido')
        
        with self.users_lock:
            if user in self.users:
                return create_response('login', 'erro', {}, self.clock,
                                     'Usuário já cadastrado')
            
            self.users.add(user)
            
            # Persiste login
            login_entry = {
                'user': user,
                'timestamp': time.time(),
                'clock': self.clock.get_time()
            }
            self.datastore.append('logins.json', login_entry)
        
        print(f"[SERVER:{self.server_name}] Novo login: {user}")
        return create_response('login', 'sucesso', {}, self.clock)
    
    def handle_list_users(self, data):
        """Retorna lista de usuários cadastrados"""
        with self.users_lock:
            users_list = list(self.users)
        
        return create_response('users', 'sucesso', {'users': users_list}, self.clock)
    
    def handle_create_channel(self, data):
        """Cria um novo canal"""
        channel = data.get('channel', '')
        
        if not channel:
            return create_response('channel', 'erro', {}, self.clock,
                                 'Nome do canal não fornecido')
        
        with self.channels_lock:
            if channel in self.channels:
                return create_response('channel', 'erro', {}, self.clock,
                                     'Canal já existe')
            
            self.channels.add(channel)
            
            # Persiste canal
            channel_entry = {
                'channel': channel,
                'timestamp': time.time(),
                'clock': self.clock.get_time()
            }
            self.datastore.append('channels.json', channel_entry)
        
        print(f"[SERVER:{self.server_name}] Novo canal: {channel}")
        return create_response('channel', 'sucesso', {}, self.clock)
    
    def handle_list_channels(self, data):
        """Retorna lista de canais disponíveis"""
        with self.channels_lock:
            channels_list = list(self.channels)
        
        return create_response('channels', 'sucesso', {'channels': channels_list}, self.clock)
    
    def handle_publish(self, data):
        """Publica mensagem em um canal"""
        user = data.get('user', '')
        channel = data.get('channel', '')
        message_text = data.get('message', '')
        
        if not channel:
            return create_response('publish', 'erro', {}, self.clock,
                                 'Nome do canal não fornecido')
        
        with self.channels_lock:
            if channel not in self.channels:
                return create_response('publish', 'erro', {}, self.clock,
                                     'Canal não existe')
        
        # Cria mensagem de publicação
        pub_data = {
            'user': user,
            'message': message_text
        }
        pub_message = create_message('publish', pub_data, self.clock)
        
        # Publica no tópico do canal
        self.pub_socket.send_multipart([channel.encode('utf-8'), pub_message])
        
        # Persiste mensagem
        with self.messages_lock:
            message_entry = {
                'type': 'publish',
                'user': user,
                'channel': channel,
                'message': message_text,
                'timestamp': time.time(),
                'clock': self.clock.get_time()
            }
            self.messages.append(message_entry)
            self.datastore.save('messages.json', self.messages)
        
        self.message_count += 1
        self._check_sync()
        
        print(f"[SERVER:{self.server_name}] Publicação em #{channel} por {user}")
        return create_response('publish', 'OK', {}, self.clock)
    
    def handle_message(self, data):
        """Envia mensagem privada para um usuário"""
        src = data.get('src', '')
        dst = data.get('dst', '')
        message_text = data.get('message', '')
        
        if not dst:
            return create_response('message', 'erro', {}, self.clock,
                                 'Destinatário não fornecido')
        
        with self.users_lock:
            if dst not in self.users:
                return create_response('message', 'erro', {}, self.clock,
                                     'Usuário destinatário não existe')
        
        # Cria mensagem privada
        msg_data = {
            'src': src,
            'message': message_text
        }
        msg_message = create_message('message', msg_data, self.clock)
        
        # Publica no tópico do usuário destinatário
        self.pub_socket.send_multipart([dst.encode('utf-8'), msg_message])
        
        # Persiste mensagem
        with self.messages_lock:
            message_entry = {
                'type': 'message',
                'src': src,
                'dst': dst,
                'message': message_text,
                'timestamp': time.time(),
                'clock': self.clock.get_time()
            }
            self.messages.append(message_entry)
            self.datastore.save('messages.json', self.messages)
        
        self.message_count += 1
        self._check_sync()
        
        print(f"[SERVER:{self.server_name}] Mensagem de {src} para {dst}")
        return create_response('message', 'OK', {}, self.clock)
    
    def handle_get_history(self, data):
        """
        Retorna histórico de mensagens de um canal específico
        
        Args:
            data: Dados da requisição com 'channel' e opcionalmente 'limit'
        
        Returns:
            Resposta com histórico de mensagens
        """
        channel = data.get('channel', '')
        limit = data.get('limit', 50)  # Padrão: últimas 50 mensagens
        
        if not channel:
            return create_response('get_history', 'erro', {}, self.clock,
                                 'Nome do canal não fornecido')
        
        with self.channels_lock:
            if channel not in self.channels:
                return create_response('get_history', 'erro', {}, self.clock,
                                     'Canal não existe')
        
        # Filtra mensagens do canal
        with self.messages_lock:
            channel_messages = [
                msg for msg in self.messages
                if msg.get('type') == 'publish' and msg.get('channel') == channel
            ]
            
            # Limita quantidade (últimas N mensagens)
            if len(channel_messages) > limit:
                channel_messages = channel_messages[-limit:]
        
        print(f"[SERVER:{self.server_name}] Histórico solicitado para #{channel}: {len(channel_messages)} mensagens")
        return create_response('get_history', 'sucesso', 
                             {'channel': channel, 'messages': channel_messages}, 
                             self.clock)
    
    def handle_get_private_history(self, data):
        """
        Retorna histórico de mensagens privadas de um usuário
        
        Args:
            data: Dados da requisição com 'user' e opcionalmente 'limit'
        
        Returns:
            Resposta com histórico de mensagens privadas
        """
        user = data.get('user', '')
        limit = data.get('limit', 50)
        
        if not user:
            return create_response('get_private_history', 'erro', {}, self.clock,
                                 'Nome do usuário não fornecido')
        
        # Filtra mensagens privadas (enviadas ou recebidas)
        with self.messages_lock:
            private_messages = [
                msg for msg in self.messages
                if msg.get('type') == 'message' and 
                   (msg.get('src') == user or msg.get('dst') == user)
            ]
            
            # Limita quantidade
            if len(private_messages) > limit:
                private_messages = private_messages[-limit:]
        
        print(f"[SERVER:{self.server_name}] Histórico privado solicitado para @{user}: {len(private_messages)} mensagens")
        return create_response('get_private_history', 'sucesso',
                             {'user': user, 'messages': private_messages},
                             self.clock)
    
    def _check_sync(self):
        """Verifica se é hora de sincronizar"""
        if self.message_count % SYNC_INTERVAL == 0:
            print(f"[SERVER:{self.server_name}] Sincronização necessária após {self.message_count} mensagens")
            # Aqui seria implementada a lógica de sincronização entre servidores
            # Por simplicidade, apenas salvamos o estado
            self._save_state()
    
    def _process_servers_topic(self):
        """Thread que processa mensagens do tópico 'servers' (anúncios de eleição)"""
        import msgpack
        
        while True:
            try:
                # Recebe mensagem do tópico 'servers'
                topic, raw_message = self.sub_socket.recv_multipart()
                message = msgpack.unpackb(raw_message, raw=False)
                
                service = message.get('service', '')
                data = message.get('data', {})
                
                # Processa anúncio de novo coordenador
                if service == 'election' and data.get('event') == 'new_coordinator':
                    new_coordinator = data.get('coordinator', '')
                    coordinator_rank = data.get('rank', 0)
                    
                    print(f"[SERVER:{self.server_name}] Anúncio recebido: {new_coordinator} é o novo coordenador (rank {coordinator_rank})")
                    
                    with self.coordinator_lock:
                        old_coordinator = self.coordinator
                        self.coordinator = new_coordinator
                        
                        # Atualiza estado de coordenação
                        if self.election_manager:
                            self.election_manager.coordinator = new_coordinator
                            self.election_manager.is_coordinator = (new_coordinator == self.server_name)
                        
                        if self.berkeley_sync:
                            self.berkeley_sync.is_coordinator = (new_coordinator == self.server_name)
                    
                    # Atualiza timestamp de heartbeat
                    self.last_coordinator_heartbeat = time.time()
                    
                    print(f"[SERVER:{self.server_name}] Coordenador atualizado: {old_coordinator} -> {new_coordinator}")
                
            except Exception as e:
                print(f"[SERVER:{self.server_name}] Erro ao processar tópico 'servers': {e}")
                time.sleep(1)
    
    def run(self):
        """Executa o loop principal do servidor"""
        print(f"[SERVER:{self.server_name}] Iniciando servidor de mensagens...")
        
        # Registra com servidor de referência
        if not self.register_with_reference():
            print(f"[SERVER:{self.server_name}] ERRO: Falha ao registrar com servidor de referência")
            return
        
        # Conecta aos sockets
        self.req_socket.connect(BROKER_BACKEND)
        print(f"[SERVER:{self.server_name}] Conectado ao broker em {BROKER_BACKEND}")
        
        self.pub_socket.connect(PROXY_BACKEND)
        print(f"[SERVER:{self.server_name}] Conectado ao proxy em {PROXY_BACKEND}")
        
        # Se inscreve no tópico 'servers' para receber anúncios de eleição
        self.sub_socket.connect("tcp://proxy:5558")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, 'servers')
        print(f"[SERVER:{self.server_name}] Inscrito no tópico 'servers'")
        
        # Inicia thread para processar mensagens do tópico 'servers'
        servers_thread = Thread(target=self._process_servers_topic, daemon=True)
        servers_thread.start()
        
        # Inicia thread de heartbeat
        heartbeat_thread = Thread(target=self.send_heartbeat, daemon=True)
        heartbeat_thread.start()
        
        print(f"[SERVER:{self.server_name}] Servidor pronto para receber requisições")
        
        try:
            while True:
                # Recebe requisição do broker
                raw_message = self.req_socket.recv()
                message = parse_message(raw_message)
                
                if not message:
                    # Envia erro se mensagem inválida
                    error = create_response('error', 'erro', {}, self.clock,
                                          'Mensagem inválida')
                    self.req_socket.send(error)
                    continue
                
                service = message.get('service', '')
                data = message.get('data', {})
                
                # Atualiza relógio lógico
                received_clock = data.get('clock', 0)
                update_logical_clock(self.clock, received_clock)
                
                # Processa requisição baseado no serviço
                if service == 'login':
                    response = self.handle_login(data)
                    self.message_count += 1
                elif service == 'users':
                    response = self.handle_list_users(data)
                    self.message_count += 1
                elif service == 'channel':
                    response = self.handle_create_channel(data)
                    self.message_count += 1
                elif service == 'channels':
                    response = self.handle_list_channels(data)
                    self.message_count += 1
                elif service == 'publish':
                    response = self.handle_publish(data)
                    # publish já incrementa message_count e chama _check_sync()
                elif service == 'message':
                    response = self.handle_message(data)
                    # message já incrementa message_count e chama _check_sync()
                elif service == 'get_history':
                    response = self.handle_get_history(data)
                    self.message_count += 1
                elif service == 'get_private_history':
                    response = self.handle_get_private_history(data)
                    self.message_count += 1
                else:
                    response = create_response(service, 'erro', {}, self.clock,
                                             f'Serviço desconhecido: {service}')
                
                # Envia resposta
                self.req_socket.send(response)
                
                # CORREÇÃO: Verifica sincronização após cada requisição processada
                # Sincroniza (Berkeley + Replicação) a cada SYNC_INTERVAL mensagens
                self._check_sync()
                
        except KeyboardInterrupt:
            print(f"\n[SERVER:{self.server_name}] Encerrando servidor...")
        finally:
            self._save_state()
            
            # Cleanup de replicação
            if self.replication_manager:
                self.replication_manager.cleanup()
            
            # Cleanup de eleição
            if self.election_manager:
                self.election_manager.cleanup()
            
            self.req_socket.close()
            self.pub_socket.close()
            self.ref_socket.close()
            self.sub_socket.close()
            self.server_socket.close()
            self.context.term()

def main():
    """Função principal"""
    # Pega nome do servidor da variável de ambiente
    server_name = os.environ.get('SERVER_NAME', None)
    
    server = MessageServer(server_name)
    server.run()

if __name__ == '__main__':
    main()
