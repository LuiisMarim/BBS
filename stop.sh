#!/bin/bash
# Script para parar o sistema BBS

echo "==================================="
echo "Sistema BBS - Encerrando"
echo "==================================="
echo ""

cd docker || exit 1

echo "🛑 Parando containers..."
docker compose down

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Sistema encerrado com sucesso!"
else
    echo ""
    echo "❌ Erro ao encerrar sistema!"
    exit 1
fi

echo ""
echo "Para remover também os dados persistidos, execute:"
echo "  cd docker && docker compose down -v"
echo ""
