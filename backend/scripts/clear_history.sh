#!/bin/bash
# Script para executar no servidor de produção via SSH
# 
# USO NO SERVIDOR DE PRODUÇÃO:
# 1. Copie este script para o servidor
# 2. Execute: bash clear_history.sh
#
# OU execute diretamente via docker exec:
# docker exec -it <container_mongodb> mongosh sigesc_db --eval "db.student_history.deleteMany({})"

echo "============================================"
echo "  LIMPEZA DE HISTÓRICO DE ALUNOS - SIGESC"
echo "============================================"
echo ""

# Verifica se mongosh está disponível
if command -v mongosh &> /dev/null; then
    MONGO_CMD="mongosh"
elif command -v mongo &> /dev/null; then
    MONGO_CMD="mongo"
else
    echo "ERRO: mongosh ou mongo não encontrado!"
    echo ""
    echo "Execute diretamente no container MongoDB:"
    echo "  docker exec -it <container_mongodb> mongosh sigesc_db --eval \"db.student_history.deleteMany({})\""
    exit 1
fi

# Preview
echo "Contando registros..."
COUNT=$($MONGO_CMD sigesc_db --quiet --eval "db.student_history.countDocuments({})")
echo ""
echo "Total de registros encontrados: $COUNT"
echo ""

if [ "$COUNT" -eq "0" ]; then
    echo "Nenhum registro para apagar."
    exit 0
fi

# Mostra exemplos
echo "Exemplos de registros:"
$MONGO_CMD sigesc_db --quiet --eval "db.student_history.find({}, {_id:0, student_id:1, action_type:1, action_date:1}).limit(3).forEach(doc => print(JSON.stringify(doc)))"
echo ""

# Confirmação
echo "⚠️  ATENÇÃO: Esta ação é IRREVERSÍVEL!"
read -p "Digite 'SIM' para confirmar a exclusão: " CONFIRM

if [ "$CONFIRM" != "SIM" ]; then
    echo "Operação cancelada."
    exit 0
fi

# Executa
echo ""
echo "Apagando registros..."
RESULT=$($MONGO_CMD sigesc_db --quiet --eval "db.student_history.deleteMany({}).deletedCount")
echo ""
echo "✅ $RESULT registros apagados com sucesso!"

# Log
$MONGO_CMD sigesc_db --quiet --eval "db.admin_logs.insertOne({action: 'clear_student_history', deleted_count: $RESULT, executed_at: new Date().toISOString(), description: 'Limpeza manual via script'})"
echo "Log registrado."
