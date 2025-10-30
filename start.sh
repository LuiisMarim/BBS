#!/bin/bash
# Script para iniciar o sistema BBS

echo "==================================="
echo "Sistema BBS - Inicializando"
echo "==================================="
echo ""

# Verifica se Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não está instalado!"
    echo "Por favor, instale o Docker antes de continuar."
    exit 1
fi

# Verifica se Docker Compose está instalado
if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose não está instalado!"
    echo "Por favor, instale o Docker Compose antes de continuar."
    exit 1
fi

echo "✅ Docker e Docker Compose encontrados"
echo ""

# Navega para o diretório docker
cd docker || exit 1

echo "📦 Construindo imagens Docker..."
docker compose build

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Erro ao construir imagens!"
    exit 1
fi

echo ""
echo "✅ Imagens construídas com sucesso!"
echo ""

echo "🚀 Iniciando containers..."
docker compose up -d

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Erro ao iniciar containers!"
    exit 1
fi

echo ""
echo "✅ Sistema iniciado com sucesso!"
echo ""
echo "==================================="
echo "Comandos úteis:"
echo "==================================="
echo ""
echo "  Ver logs de todos os containers:"
echo "    docker compose logs -f"
echo ""
echo "  Ver logs de um container específico:"
echo "    docker compose logs -f <nome_container>"
echo ""
echo "  Acessar o cliente interativo:"
echo "    docker attach bbs_client"
echo ""
echo "  Parar o sistema:"
echo "    docker compose down"
echo ""
echo "  Parar e remover volumes:"
echo "    docker compose down -v"
echo ""
echo "==================================="
echo "Aguarde alguns segundos para os serviços iniciarem completamente..."
echo "==================================="
