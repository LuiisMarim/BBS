"""
Módulo de Mensagens
Funções auxiliares para criação e serialização de mensagens com MessagePack
"""

import msgpack
import time
from typing import Any, Dict

def create_message(service: str, data: Dict, logical_clock) -> bytes:
    """
    Cria uma mensagem serializada com MessagePack
    
    Args:
        service: Nome do serviço
        data: Dados da mensagem
        logical_clock: Instância do relógio lógico
    
    Returns:
        Mensagem serializada em bytes
    """
    # Incrementa o relógio antes de enviar
    clock_value = logical_clock.increment()
    
    # Adiciona timestamp e clock aos dados
    data['timestamp'] = time.time()
    data['clock'] = clock_value
    
    message = {
        'service': service,
        'data': data
    }
    
    return msgpack.packb(message, use_bin_type=True)

def parse_message(raw_message: bytes) -> Dict[str, Any]:
    """
    Deserializa uma mensagem MessagePack
    
    Args:
        raw_message: Mensagem em bytes
    
    Returns:
        Dicionário com a mensagem deserializada
    """
    try:
        return msgpack.unpackb(raw_message, raw=False)
    except Exception as e:
        print(f"Erro ao deserializar mensagem: {e}")
        return {}

def create_response(service: str, status: str, data: Dict, logical_clock, description: str = None) -> bytes:
    """
    Cria uma mensagem de resposta
    
    Args:
        service: Nome do serviço
        status: Status da resposta ('sucesso' ou 'erro')
        data: Dados adicionais da resposta
        logical_clock: Instância do relógio lógico
        description: Descrição de erro opcional (conforme especificação Parte 1)
    
    Returns:
        Resposta serializada em bytes
    """
    clock_value = logical_clock.increment()
    
    response_data = {
        'status': status,
        'timestamp': time.time(),
        'clock': clock_value
    }
    
    if description:
        response_data['description'] = description
    
    # Mescla dados adicionais
    response_data.update(data)
    
    response = {
        'service': service,
        'data': response_data
    }
    
    return msgpack.packb(response, use_bin_type=True)

def update_logical_clock(logical_clock, received_clock: int):
    """
    Atualiza o relógio lógico com base no valor recebido
    
    Args:
        logical_clock: Instância do relógio lógico
        received_clock: Valor do relógio recebido
    """
    logical_clock.update(received_clock)
