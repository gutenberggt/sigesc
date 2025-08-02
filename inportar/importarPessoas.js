const admin = require('firebase-admin');
const fs = require('fs');
const csv = require('csv-parser');

// --- CONFIGURAÇÃO ---
const serviceAccount = require('./serviceAccountKey.json');
const CSV_FILE_PATH = './pessoas.csv'; 
// --------------------

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();
const pessoasCollection = db.collection('pessoas');

async function importarPessoas() {
  const pessoasParaAdicionar = [];
  
  fs.createReadStream(CSV_FILE_PATH)
    .pipe(csv({ separator: ';' }))
    .on('data', (row) => {
      const pessoaData = {
        nomeCompleto: row.nomeCompleto?.toUpperCase() || '',
        cpf: row.cpf?.replace(/\D/g, '') || '',
        dataNascimento: row.dataNascimento || '',
        sexo: row.sexo || 'Nao Informado',
        emailContato: row.emailContato?.toLowerCase() || '',
        pessoaMae: row.pessoaMae?.toUpperCase() || '',
        pessoaPai: row.pessoaPai?.toUpperCase() || '',
        enderecoLogradouro: row.enderecoLogradouro?.toUpperCase() || '',
        enderecoNumero: row.enderecoNumero || '',
        enderecoBairro: row.enderecoBairro?.toUpperCase() || '',
        municipioResidencia: row.municipioResidencia?.toUpperCase() || '',
        cep: row.cep?.replace(/\D/g, '') || '',
        dataCadastro: new Date(),
        ultimaAtualizacao: new Date(),
      };
      
      if (pessoaData.nomeCompleto && pessoaData.cpf && pessoaData.emailContato) {
        pessoasParaAdicionar.push(pessoaData);
      } else {
        console.warn(`Linha ignorada por falta de dados essenciais:`, row);
      }
    })
    .on('end', async () => {
      console.log(`Leitura do CSV concluída. ${pessoasParaAdicionar.length} pessoas prontas para importação.`);
      
      for (const pessoa of pessoasParaAdicionar) {
        try {
          const existingPerson = await pessoasCollection.where('cpf', '==', pessoa.cpf).get();

          if (!existingPerson.empty) {
            console.log(`Pessoa com CPF ${pessoa.cpf} (${pessoa.nomeCompleto}) já existe. A ignorar.`);
            continue;
          }

          // ======================= INÍCIO DA CORREÇÃO =======================
          // CORREÇÃO: Sintaxe de adicionar documento ajustada para o Firebase Admin SDK
          const docRef = await pessoasCollection.add(pessoa);
          // ======================== FIM DA CORREÇÃO =========================

          console.log(`Pessoa "${pessoa.nomeCompleto}" adicionada com sucesso. Documento ID: ${docRef.id}`);

        } catch (error) {
          console.error(`Erro ao adicionar a pessoa "${pessoa.nomeCompleto}":`, error.message);
        }
      }
      console.log('Processo de importação concluído.');
    });
}

importarPessoas();