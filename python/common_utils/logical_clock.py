"""
Módulo de Relógio Lógico de Lamport
Implementa o contador lógico para sincronização de eventos distribuídos
"""

class LogicalClock:
    """Implementação do Relógio Lógico de Lamport"""
    
    def __init__(self):
        """Inicializa o contador do relógio lógico em 0"""
        self.counter = 0
    
    def increment(self):
        """
        Incrementa o contador antes de enviar uma mensagem
        Retorna o novo valor do contador
        """
        self.counter += 1
        return self.counter
    
    def update(self, received_time):
        """
        Atualiza o relógio ao receber uma mensagem
        Usa o máximo entre o contador atual e o recebido, depois incrementa
        
        Args:
            received_time: Valor do relógio recebido na mensagem
        
        Returns:
            Novo valor do contador
        """
        self.counter = max(self.counter, received_time) + 1
        return self.counter
    
    def get_time(self):
        """Retorna o valor atual do contador sem modificá-lo"""
        return self.counter
