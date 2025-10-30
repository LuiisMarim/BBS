#!/bin/bash
# Script para verificar status do sistema BBS

echo "==================================="
echo "Sistema BBS - Status"
echo "==================================="
echo ""

cd docker || exit 1

echo "📊 Status dos containers:"
echo ""
docker compose ps

echo ""
echo "==================================="
echo "📈 Estatísticas de uso:"
echo "==================================="
echo ""
docker stats --no-stream $(docker compose ps -q)

echo ""
echo "==================================="
echo "💾 Volumes criados:"
echo "==================================="
echo ""
docker volume ls | grep bbs

echo ""
echo "==================================="
echo "🌐 Rede:"
echo "==================================="
echo ""
docker network inspect bbs_network 2>/dev/null | grep -A 5 "Name\|Containers" || echo "Rede não encontrada"

echo ""
