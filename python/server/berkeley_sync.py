#!/usr/bin/env python3
"""
Módulo de Sincronização de Relógio Físico - Algoritmo de Berkeley
Implementa sincronização de tempo entre servidores distribuídos
"""

import time
from typing import List, Dict, Tuple
import zmq

class BerkeleySynchronizer:
    """
    Implementação do algoritmo de Berkeley para sincronização de relógios
    
    O coordenador coleta timestamps de todos os servidores, calcula o offset
    médio e distribui ajustes para sincronização.
    """
    
    def __init__(self, server_name: str, is_coordinator: bool = False, datastore=None):
        """
        Inicializa o sincronizador
        
        Args:
            server_name: Nome do servidor
            is_coordinator: Se este servidor é o coordenador
            datastore: Instância do DataStore para persistência
        """
        self.server_name = server_name
        self.is_coordinator = is_coordinator
        self.time_offset = 0.0  # Offset aplicado ao relógio local
        self.sync_history = []  # Histórico de sincronizações
        self.datastore = datastore
        
    def get_local_time(self) -> float:
        """
        Retorna o tempo local ajustado com o offset
        
        Returns:
            Timestamp ajustado
        """
        return time.time() + self.time_offset
    
    def collect_timestamps(self, server_list: List[Dict]) -> Dict[str, float]:
        """
        Coordenador coleta timestamps de todos os servidores
        
        Args:
            server_list: Lista de servidores ativos [{name, address}, ...]
        
        Returns:
            Dicionário {server_name: timestamp}
        """
        timestamps = {}
        
        # Adiciona timestamp do próprio coordenador
        timestamps[self.server_name] = self.get_local_time()
        
        # Cria contexto temporário para requisições
        context = zmq.Context()
        
        for server in server_list:
            if server['name'] == self.server_name:
                continue
                
            try:
                # Socket REQ para solicitar timestamp
                socket = context.socket(zmq.REQ)
                socket.setsockopt(zmq.RCVTIMEO, 2000)  # Timeout 2s
                socket.setsockopt(zmq.SNDTIMEO, 2000)
                
                address = f"tcp://{server['name']}:6000"
                socket.connect(address)
                
                # Solicita timestamp
                import msgpack
                request = msgpack.packb({
                    'service': 'get_time',
                    'data': {'requester': self.server_name}
                })
                
                socket.send(request)
                
                # Recebe resposta
                raw_response = socket.recv()
                response = msgpack.unpackb(raw_response, raw=False)
                
                if response.get('data', {}).get('time'):
                    timestamps[server['name']] = response['data']['time']
                
                socket.close()
                
            except Exception as e:
                print(f"[BERKELEY] Erro ao coletar timestamp de {server['name']}: {e}")
                continue
        
        context.term()
        return timestamps
    
    def calculate_offsets(self, timestamps: Dict[str, float]) -> Dict[str, float]:
        """
        Calcula offsets necessários para cada servidor
        
        Args:
            timestamps: Dicionário {server_name: timestamp}
        
        Returns:
            Dicionário {server_name: offset}
        """
        if not timestamps:
            return {}
        
        # Calcula tempo médio
        avg_time = sum(timestamps.values()) / len(timestamps)
        
        # Calcula offset para cada servidor
        offsets = {}
        for server_name, timestamp in timestamps.items():
            offsets[server_name] = avg_time - timestamp
        
        print(f"[BERKELEY] Tempo médio: {avg_time:.6f}")
        print(f"[BERKELEY] Offsets calculados: {offsets}")
        
        return offsets
    
    def distribute_offsets(self, offsets: Dict[str, float], server_list: List[Dict]):
        """
        Distribui offsets para todos os servidores
        
        Args:
            offsets: Dicionário {server_name: offset}
            server_list: Lista de servidores ativos
        """
        context = zmq.Context()
        
        for server in server_list:
            server_name = server['name']
            
            if server_name == self.server_name:
                # Aplica offset no próprio coordenador
                self.apply_offset(offsets.get(server_name, 0.0))
                continue
            
            if server_name not in offsets:
                continue
            
            try:
                socket = context.socket(zmq.REQ)
                socket.setsockopt(zmq.RCVTIMEO, 2000)
                socket.setsockopt(zmq.SNDTIMEO, 2000)
                
                address = f"tcp://{server_name}:6000"
                socket.connect(address)
                
                # Envia offset
                import msgpack
                request = msgpack.packb({
                    'service': 'apply_offset',
                    'data': {
                        'offset': offsets[server_name],
                        'coordinator': self.server_name,
                        'timestamp': time.time()
                    }
                })
                
                socket.send(request)
                
                # Aguarda confirmação
                raw_response = socket.recv()
                response = msgpack.unpackb(raw_response, raw=False)
                
                if response.get('data', {}).get('status') == 'success':
                    print(f"[BERKELEY] Offset aplicado em {server_name}: {offsets[server_name]:.6f}s")
                
                socket.close()
                
            except Exception as e:
                print(f"[BERKELEY] Erro ao distribuir offset para {server_name}: {e}")
        
        context.term()
    
    def apply_offset(self, offset: float):
        """
        Aplica offset ao relógio local
        
        Args:
            offset: Valor do offset em segundos
        """
        self.time_offset += offset
        
        # Registra no histórico
        sync_record = {
            'timestamp': time.time(),
            'offset_applied': offset,
            'total_offset': self.time_offset
        }
        self.sync_history.append(sync_record)
        
        # Persiste histórico
        if self.datastore:
            self.datastore.save_replication(f'berkeley_sync_{self.server_name}', {
                'server': self.server_name,
                'time_offset': self.time_offset,
                'sync_history': self.sync_history
            })
        
        print(f"[BERKELEY] Offset aplicado: {offset:.6f}s (total: {self.time_offset:.6f}s)")
    
    def run_synchronization(self, server_list: List[Dict]) -> bool:
        """
        Executa uma rodada completa de sincronização (coordenador)
        
        Args:
            server_list: Lista de servidores ativos
        
        Returns:
            True se sincronização foi bem-sucedida
        """
        if not self.is_coordinator:
            print(f"[BERKELEY] {self.server_name} não é coordenador, ignorando sincronização")
            return False
        
        print(f"[BERKELEY] Iniciando sincronização de relógio como coordenador")
        
        try:
            # Passo 1: Coletar timestamps
            timestamps = self.collect_timestamps(server_list)
            
            if len(timestamps) < 2:
                print(f"[BERKELEY] Timestamps insuficientes para sincronização: {len(timestamps)}")
                return False
            
            # Passo 2: Calcular offsets
            offsets = self.calculate_offsets(timestamps)
            
            # Passo 3: Distribuir offsets
            self.distribute_offsets(offsets, server_list)
            
            print(f"[BERKELEY] Sincronização completada com sucesso")
            return True
            
        except Exception as e:
            print(f"[BERKELEY] Erro durante sincronização: {e}")
            return False
    
    def get_sync_history(self) -> List[Dict]:
        """
        Retorna histórico de sincronizações
        
        Returns:
            Lista de registros de sincronização
        """
        return self.sync_history
