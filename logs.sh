#!/bin/bash
# Script para visualizar logs do sistema BBS

echo "==================================="
echo "Sistema BBS - Visualizador de Logs"
echo "==================================="
echo ""

cd docker || exit 1

if [ -z "$1" ]; then
    echo "Mostrando logs de todos os containers..."
    echo "Pressione Ctrl+C para sair"
    echo ""
    docker compose logs -f
else
    echo "Mostrando logs de: $1"
    echo "Pressione Ctrl+C para sair"
    echo ""
    docker compose logs -f "$1"
fi
