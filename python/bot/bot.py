#!/usr/bin/env python3
"""
Bot - Cliente Automático
Gera mensagens automaticamente em canais públicos
Conecta ao broker (5555) e ao proxy (5558)
"""

import zmq
import time
import sys
import os
import random

# Adiciona o diretório common_utils ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common_utils'))

from logical_clock import LogicalClock
from messaging import create_message, parse_message, update_logical_clock

# Configurações
BROKER_FRONTEND = "tcp://broker:5555"
PROXY_FRONTEND = "tcp://proxy:5558"

# Mensagens padrão que o bot pode enviar
BOT_MESSAGES = [
    "Olá a todos! 👋",
    "Como estão as coisas por aqui?",
    "Alguém sabe de novidades?",
    "Que dia incrível!",
    "Estou adorando este sistema distribuído!",
    "ZeroMQ é muito eficiente!",
    "MessagePack torna tudo mais rápido!",
    "Sistemas distribuídos são fascinantes!",
    "Relógios lógicos mantêm tudo sincronizado!",
    "A consistência é fundamental em sistemas distribuídos!",
    "Bora conversar pessoal!",
    "Este canal está ativo hoje!",
    "Quem mais está online?",
    "Vamos manter o chat ativo!",
    "Adorei essa discussão!",
    "Interessante o que vocês estão falando!",
    "Concordo totalmente!",
    "Faz sentido o que você disse!",
    "Ótimo ponto de vista!",
    "Nunca tinha pensado por esse ângulo!"
]

class BBSBot:
    """Bot automático para o sistema BBS"""
    
    def __init__(self, bot_id=None):
        """
        Inicializa o bot
        
        Args:
            bot_id: ID do bot (opcional, será gerado se não fornecido)
        """
        self.bot_id = bot_id or random.randint(1000, 9999)
        self.username = f"bot_{self.bot_id}"
        self.clock = LogicalClock()
        
        # Contexto ZeroMQ
        self.context = zmq.Context()
        
        # Socket REQ para broker
        self.req_socket = self.context.socket(zmq.REQ)
        
        # Socket SUB para proxy (para ouvir canais)
        self.sub_socket = self.context.socket(zmq.SUB)
        
        # Lista de canais conhecidos
        self.channels = []
        
        print(f"[BOT:{self.username}] Bot inicializado (clock: {self.clock.get_time()})")
    
    def connect(self):
        """Conecta aos serviços"""
        try:
            # Conecta ao broker
            self.req_socket.connect(BROKER_FRONTEND)
            print(f"[BOT:{self.username}] Conectado ao broker em {BROKER_FRONTEND}")
            
            # Conecta ao proxy
            self.sub_socket.connect(PROXY_FRONTEND)
            print(f"[BOT:{self.username}] Conectado ao proxy em {PROXY_FRONTEND}")
            
            return True
        except Exception as e:
            print(f"[BOT:{self.username}] Erro ao conectar: {e}")
            return False
    
    def login(self):
        """Realiza login do bot"""
        try:
            data = {'user': self.username}
            message = create_message('login', data, self.clock)
            
            self.req_socket.send(message)
            
            # Recebe resposta
            raw_response = self.req_socket.recv()
            response = parse_message(raw_response)
            
            if response and response.get('data'):
                data = response['data']
                update_logical_clock(self.clock, data.get('clock', 0))
                
                if data.get('status') == 'sucesso':
                    print(f"[BOT:{self.username}] Login realizado com sucesso")
                    return True
                else:
                    print(f"[BOT:{self.username}] Erro no login: {data.get('message', 'Desconhecido')}")
            
            return False
            
        except Exception as e:
            print(f"[BOT:{self.username}] Erro ao fazer login: {e}")
            return False
    
    def get_channels(self):
        """Obtém lista de canais disponíveis"""
        try:
            message = create_message('channels', {}, self.clock)
            self.req_socket.send(message)
            
            # Recebe resposta
            raw_response = self.req_socket.recv()
            response = parse_message(raw_response)
            
            if response and response.get('data'):
                data = response['data']
                update_logical_clock(self.clock, data.get('clock', 0))
                
                if data.get('channels'):
                    self.channels = data['channels']
                    print(f"[BOT:{self.username}] {len(self.channels)} canais encontrados")
                    return True
            
            return False
            
        except Exception as e:
            print(f"[BOT:{self.username}] Erro ao obter canais: {e}")
            return False
    
    def create_default_channels(self):
        """Cria canais padrão se não existirem"""
        default_channels = ['geral', 'tecnologia', 'random']
        
        for channel in default_channels:
            try:
                data = {'channel': channel}
                message = create_message('channel', data, self.clock)
                
                self.req_socket.send(message)
                
                # Recebe resposta
                raw_response = self.req_socket.recv()
                response = parse_message(raw_response)
                
                if response and response.get('data'):
                    data = response['data']
                    update_logical_clock(self.clock, data.get('clock', 0))
                    
                    if data.get('status') == 'sucesso':
                        print(f"[BOT:{self.username}] Canal #{channel} criado")
                
                # Pequeno delay entre criações
                time.sleep(0.5)
                
            except Exception as e:
                print(f"[BOT:{self.username}] Erro ao criar canal {channel}: {e}")
    
    def publish_message(self, channel, message_text):
        """
        Publica mensagem em um canal
        
        Args:
            channel: Nome do canal
            message_text: Texto da mensagem
        
        Returns:
            True se publicado com sucesso
        """
        try:
            data = {
                'user': self.username,
                'channel': channel,
                'message': message_text
            }
            message = create_message('publish', data, self.clock)
            
            self.req_socket.send(message)
            
            # Recebe resposta
            raw_response = self.req_socket.recv()
            response = parse_message(raw_response)
            
            if response and response.get('data'):
                data = response['data']
                update_logical_clock(self.clock, data.get('clock', 0))
                
                if data.get('status') == 'OK':
                    return True
            
            return False
            
        except Exception as e:
            print(f"[BOT:{self.username}] Erro ao publicar: {e}")
            return False
    
    def run(self):
        """Executa o loop principal do bot"""
        print(f"[BOT:{self.username}] Iniciando bot...")
        
        # Conecta aos serviços
        if not self.connect():
            print(f"[BOT:{self.username}] Falha ao conectar. Encerrando...")
            return
        
        # Faz login
        if not self.login():
            print(f"[BOT:{self.username}] Falha no login. Tentando novamente em 5s...")
            time.sleep(5)
            if not self.login():
                print(f"[BOT:{self.username}] Falha definitiva no login. Encerrando...")
                return
        
        # Aguarda um pouco para garantir que o sistema está estável
        time.sleep(2)
        
        # Cria canais padrão
        print(f"[BOT:{self.username}] Criando canais padrão...")
        self.create_default_channels()
        
        # Aguarda canais serem criados
        time.sleep(2)
        
        # Obtém lista de canais
        if not self.get_channels():
            print(f"[BOT:{self.username}] Aviso: Não foi possível obter canais")
            # Usa canais padrão
            self.channels = ['geral', 'tecnologia', 'random']
        
        if not self.channels:
            print(f"[BOT:{self.username}] Nenhum canal disponível. Criando canal padrão...")
            self.channels = ['geral']
        
        print(f"[BOT:{self.username}] Bot pronto! Iniciando publicações...")
        
        message_count = 0
        
        try:
            while True:
                # Escolhe canal aleatório
                channel = random.choice(self.channels)
                
                # Envia 10 mensagens no canal escolhido
                print(f"\n[BOT:{self.username}] Enviando 10 mensagens para #{channel}")
                
                for i in range(10):
                    # Escolhe mensagem aleatória
                    message_text = random.choice(BOT_MESSAGES)
                    
                    # Publica mensagem
                    success = self.publish_message(channel, message_text)
                    
                    if success:
                        message_count += 1
                        print(f"[BOT:{self.username}] Mensagem {i+1}/10 enviada para #{channel} "
                              f"(total: {message_count}, clock: {self.clock.get_time()})")
                    else:
                        print(f"[BOT:{self.username}] Falha ao enviar mensagem {i+1}/10")
                    
                    # Delay entre mensagens (2-5 segundos)
                    time.sleep(random.uniform(2, 5))
                
                # Delay maior antes de escolher novo canal (5-10 segundos)
                print(f"[BOT:{self.username}] Aguardando antes de escolher novo canal...")
                time.sleep(random.uniform(5, 10))
                
                # Atualiza lista de canais periodicamente
                if message_count % 50 == 0:
                    self.get_channels()
                
        except KeyboardInterrupt:
            print(f"\n[BOT:{self.username}] Encerrando bot...")
        finally:
            self.req_socket.close()
            self.sub_socket.close()
            self.context.term()

def main():
    """Função principal"""
    # Pega ID do bot da variável de ambiente se disponível
    bot_id = os.environ.get('BOT_ID', None)
    if bot_id:
        bot_id = int(bot_id)
    
    bot = BBSBot(bot_id)
    bot.run()

if __name__ == '__main__':
    main()
