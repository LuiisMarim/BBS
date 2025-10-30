"""
Módulo de Persistência Local
Gerencia leitura e escrita de dados em arquivos JSON
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

class DataStore:
    """Gerenciador de persistência local em JSON"""
    
    def __init__(self, data_dir: str = "/data"):
        """
        Inicializa o gerenciador de persistência
        
        Args:
            data_dir: Diretório raiz para armazenamento de dados
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdiretório para replicação
        self.replication_dir = self.data_dir / "replication"
        self.replication_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self, filename: str, default: Any = None) -> Any:
        """
        Carrega dados de um arquivo JSON
        
        Args:
            filename: Nome do arquivo (ex: 'logins.json')
            default: Valor padrão se o arquivo não existir
        
        Returns:
            Dados carregados ou valor padrão
        """
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            return default if default is not None else []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Erro ao carregar {filename}: {e}")
            return default if default is not None else []
    
    def save(self, filename: str, data: Any) -> bool:
        """
        Salva dados em um arquivo JSON
        
        Args:
            filename: Nome do arquivo
            data: Dados a serem salvos
        
        Returns:
            True se salvo com sucesso, False caso contrário
        """
        filepath = self.data_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"Erro ao salvar {filename}: {e}")
            return False
    
    def append(self, filename: str, item: Any) -> bool:
        """
        Adiciona um item a uma lista existente
        
        Args:
            filename: Nome do arquivo
            item: Item a ser adicionado
        
        Returns:
            True se adicionado com sucesso
        """
        data = self.load(filename, default=[])
        if not isinstance(data, list):
            data = [data]
        data.append(item)
        return self.save(filename, data)
    
    def save_replication(self, server_name: str, data: Dict) -> bool:
        """
        Salva dados de replicação específicos de um servidor
        
        Args:
            server_name: Nome do servidor
            data: Dados a replicar
        
        Returns:
            True se salvo com sucesso
        """
        filepath = self.replication_dir / f"{server_name}.json"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"Erro ao salvar replicação para {server_name}: {e}")
            return False
    
    def load_replication(self, server_name: str) -> Dict:
        """
        Carrega dados de replicação de um servidor
        
        Args:
            server_name: Nome do servidor
        
        Returns:
            Dados de replicação ou dicionário vazio
        """
        filepath = self.replication_dir / f"{server_name}.json"
        
        if not filepath.exists():
            return {}
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Erro ao carregar replicação de {server_name}: {e}")
            return {}
