const { Client } = require('pg');

const client = new Client({
  connectionString: process.env.DATABASE_URL,
  ssl: {
    rejectUnauthorized: false
  }
});

const STHS = [
  { codigo: 'STH-001', sop: 'SOP-100', sub_sop: 'SOP-100A', descricao: 'Sistema de agua de resfriamento - Anel Norte', status: 'PENDENTE' },
  { codigo: 'STH-002', sop: 'SOP-100', sub_sop: 'SOP-100B', descricao: 'Sistema de agua de resfriamento - Anel Sul', status: 'PENDENTE' },
  { codigo: 'STH-003', sop: 'SOP-200', sub_sop: 'SOP-200A', descricao: 'Sistema de vapor de alta pressao', status: 'EM_EXECUCAO' },
  { codigo: 'STH-004', sop: 'SOP-200', sub_sop: 'SOP-200B', descricao: 'Sistema de condensado de retorno', status: 'EM_EXECUCAO' },
  { codigo: 'STH-005', sop: 'SOP-300', sub_sop: 'SOP-300A', descricao: 'Sistema de oleo termico - Circuito primario', status: 'CONCLUIDO' },
  { codigo: 'STH-006', sop: 'SOP-300', sub_sop: 'SOP-300B', descricao: 'Sistema de oleo termico - Circuito secundario', status: 'PENDENTE' },
  { codigo: 'STH-007', sop: 'SOP-400', sub_sop: 'SOP-400A', descricao: 'Sistema de gas combustivel - Alimentacao fornos', status: 'PENDENTE' },
  { codigo: 'STH-008', sop: 'SOP-500', sub_sop: 'SOP-500A', descricao: 'Sistema de ar comprimido - Instrumentacao', status: 'EM_EXECUCAO' },
  { codigo: 'STH-009', sop: 'SOP-500', sub_sop: 'SOP-500B', descricao: 'Sistema de ar comprimido - Servico', status: 'PENDENTE' },
  { codigo: 'STH-010', sop: 'SOP-600', sub_sop: 'SOP-600A', descricao: 'Sistema de nitrogenio - Inertizacao', status: 'CONCLUIDO' },
  { codigo: 'STH-0034-0136-0055-001-01-001', sop: 'SOP-100', sub_sop: 'SOP-100A', descricao: 'Sistema de agua de resfriamento - Teste Hidrostatico Linha Principal', status: 'PENDENTE' },
];

const LINHAS_TUBULACAO = [
  { numero_linha: '2"-CW-001-A1A-N', tag: 'CW-001', malha: 'CW-M01', sistema: 'Agua de Resfriamento', sop: 'SOP-100', sub_sop: 'SOP-100A', sth: 'STH-001', pressao_teste: 15.0, descricao_sistema: 'Linha de alimentacao do trocador E-101' },
  { numero_linha: '4"-CW-002-A1A-N', tag: 'CW-002', malha: 'CW-M01', sistema: 'Agua de Resfriamento', sop: 'SOP-100', sub_sop: 'SOP-100A', sth: 'STH-001', pressao_teste: 15.0, descricao_sistema: 'Linha de retorno do trocador E-101' },
  { numero_linha: '6"-CW-003-A1B-N', tag: 'CW-003', malha: 'CW-M02', sistema: 'Agua de Resfriamento', sop: 'SOP-100', sub_sop: 'SOP-100B', sth: 'STH-002', pressao_teste: 12.5, descricao_sistema: 'Linha de alimentacao do trocador E-201' },
  { numero_linha: '8"-ST-001-B2A-H', tag: 'ST-001', malha: 'ST-M01', sistema: 'Vapor de Alta', sop: 'SOP-200', sub_sop: 'SOP-200A', sth: 'STH-003', pressao_teste: 65.0, descricao_sistema: 'Linha principal de vapor para turbina T-101' },
  { numero_linha: '4"-ST-002-B2A-H', tag: 'ST-002', malha: 'ST-M01', sistema: 'Vapor de Alta', sop: 'SOP-200', sub_sop: 'SOP-200A', sth: 'STH-003', pressao_teste: 65.0, descricao_sistema: 'Derivacao de vapor para aquecedor H-101' },
  { numero_linha: '3"-CD-001-B2B-H', tag: 'CD-001', malha: 'CD-M01', sistema: 'Condensado', sop: 'SOP-200', sub_sop: 'SOP-200B', sth: 'STH-004', pressao_teste: 25.0, descricao_sistema: 'Retorno de condensado da turbina T-101' },
  { numero_linha: '6"-OT-001-C3A-H', tag: 'OT-001', malha: 'OT-M01', sistema: 'Oleo Termico', sop: 'SOP-300', sub_sop: 'SOP-300A', sth: 'STH-005', pressao_teste: 18.0, descricao_sistema: 'Linha de oleo termico quente para reator R-101' },
  { numero_linha: '6"-OT-002-C3A-H', tag: 'OT-002', malha: 'OT-M01', sistema: 'Oleo Termico', sop: 'SOP-300', sub_sop: 'SOP-300A', sth: 'STH-005', pressao_teste: 18.0, descricao_sistema: 'Linha de retorno oleo termico do reator R-101' },
  { numero_linha: '3"-FG-001-D4A-F', tag: 'FG-001', malha: 'FG-M01', sistema: 'Gas Combustivel', sop: 'SOP-400', sub_sop: 'SOP-400A', sth: 'STH-007', pressao_teste: 8.5, descricao_sistema: 'Alimentacao de gas combustivel para forno F-101' },
  { numero_linha: '2"-IA-001-E5A-N', tag: 'IA-001', malha: 'IA-M01', sistema: 'Ar Instrumentacao', sop: 'SOP-500', sub_sop: 'SOP-500A', sth: 'STH-008', pressao_teste: 12.0, descricao_sistema: 'Distribuicao de ar de instrumentacao - Area 1' },
  { numero_linha: '3"-IA-002-E5A-N', tag: 'IA-002', malha: 'IA-M01', sistema: 'Ar Instrumentacao', sop: 'SOP-500', sub_sop: 'SOP-500A', sth: 'STH-008', pressao_teste: 12.0, descricao_sistema: 'Header principal de ar de instrumentacao' },
  { numero_linha: '2"-SA-001-E5B-N', tag: 'SA-001', malha: 'SA-M01', sistema: 'Ar de Servico', sop: 'SOP-500', sub_sop: 'SOP-500B', sth: 'STH-009', pressao_teste: 10.5, descricao_sistema: 'Ar de servico para oficina mecanica' },
  { numero_linha: '2"-N2-001-F6A-N', tag: 'N2-001', malha: 'N2-M01', sistema: 'Nitrogenio', sop: 'SOP-600', sub_sop: 'SOP-600A', sth: 'STH-010', pressao_teste: 20.0, descricao_sistema: 'Linha de nitrogenio para inertizacao de vasos' },
  { numero_linha: '1"-N2-002-F6A-N', tag: 'N2-002', malha: 'N2-M01', sistema: 'Nitrogenio', sop: 'SOP-600', sub_sop: 'SOP-600A', sth: 'STH-010', pressao_teste: 20.0, descricao_sistema: 'Ponto de purga com nitrogenio - Coluna C-101' },
  { numero_linha: '4"-OT-003-C3B-H', tag: 'OT-003', malha: 'OT-M02', sistema: 'Oleo Termico', sop: 'SOP-300', sub_sop: 'SOP-300B', sth: 'STH-006', pressao_teste: 16.0, descricao_sistema: 'Circuito secundario oleo termico - Tanque TQ-301' },
];

const MODELOS_RELATORIO = [
  {
    nome: 'Teste Hidrostatico - Tubulacao',
    descricao: 'Modelo padrao para registro de teste hidrostatico em linhas de tubulacao conforme ASME B31.3',
    tipo: 'TESTE_HIDROSTATICO',
    caminho_template: '/templates/teste_hidrostatico_tubulacao.pdf',
    campos: JSON.stringify({ pressao_teste: 'number', pressao_minima: 'number', duracao_min: 'number', fluido_teste: 'string', temperatura_ambiente: 'number', manometro_tag: 'string', resultado: 'string' }),
    campos_template: JSON.stringify({ titulo: 'Registro de Teste Hidrostatico', versao: '2.0', norma_ref: 'ASME B31.3' }),
    ativo: true
  },
  {
    nome: 'Descarga de Linha',
    descricao: 'Registro de descarga e limpeza de linhas de tubulacao antes do comissionamento',
    tipo: 'DESCARGA_LINHA',
    caminho_template: '/templates/descarga_linha.pdf',
    campos: JSON.stringify({ metodo_limpeza: 'string', fluido_limpeza: 'string', volume_descarga: 'number', ph_entrada: 'number', ph_saida: 'number', resultado: 'string' }),
    campos_template: JSON.stringify({ titulo: 'Registro de Descarga de Linha', versao: '1.0' }),
    ativo: true
  },
  {
    nome: 'Flush Line',
    descricao: 'Procedimento de flushing para remocao de debris e contaminantes da tubulacao',
    tipo: 'FLUSH_LINE',
    caminho_template: '/templates/flush_line.pdf',
    campos: JSON.stringify({ vazao_flush: 'number', duracao_min: 'number', turbidez_entrada: 'number', turbidez_saida: 'number', num_ciclos: 'number', resultado: 'string' }),
    campos_template: JSON.stringify({ titulo: 'Registro de Flush Line', versao: '1.5' }),
    ativo: true
  },
  {
    nome: 'Teste de Estanqueidade',
    descricao: 'Teste pneumatico de estanqueidade para deteccao de vazamentos em juntas e conexoes',
    tipo: 'TESTE_ESTANQUEIDADE',
    caminho_template: '/templates/teste_estanqueidade.pdf',
    campos: JSON.stringify({ pressao_teste: 'number', duracao_min: 'number', fluido_teste: 'string', metodo_deteccao: 'string', pontos_verificados: 'number', vazamentos_encontrados: 'number', resultado: 'string' }),
    campos_template: JSON.stringify({ titulo: 'Registro de Teste de Estanqueidade', versao: '1.0', norma_ref: 'ASME B31.3 Cap. VI' }),
    ativo: true
  },
  {
    nome: 'Certificado de Teste',
    descricao: 'Certificado consolidado de conclusao dos testes de comissionamento de um sistema',
    tipo: 'CERTIFICADO_TESTE',
    caminho_template: '/templates/certificado_teste.pdf',
    campos: JSON.stringify({ sistema: 'string', data_inicio: 'date', data_conclusao: 'date', responsavel_execucao: 'string', responsavel_aprovacao: 'string', resultado_global: 'string', observacoes: 'string' }),
    campos_template: JSON.stringify({ titulo: 'Certificado de Conclusao de Testes', versao: '3.0' }),
    ativo: true
  },
];

async function seed() {
  try {
    await client.connect();
    console.log('Conectado ao banco.\n');

    await client.query('BEGIN');

    console.log('>> Resetando sequences...');
    await client.query("SELECT setval('sths_id_seq', 1, false)");
    await client.query("SELECT setval('linhas_tubulacao_id_seq', 1, false)");
    await client.query("SELECT setval('modelos_relatorio_id_seq', 1, false)");

    console.log('>> Limpando tabelas (ordem respeitando FKs)...');
    await client.query('DELETE FROM relatorios_execucao');
    await client.query('DELETE FROM relatorios');
    await client.query('DELETE FROM pasta_testes');
    await client.query('DELETE FROM documentos_pasta');
    await client.query('DELETE FROM pasta_linhas');
    await client.query('DELETE FROM pastas_teste');
    await client.query('DELETE FROM spools');
    await client.query('DELETE FROM documentos_linha');
    await client.query('DELETE FROM sth_linhas');
    await client.query('DELETE FROM linhas_tubulacao');
    await client.query('DELETE FROM linhas_tubulacao_catalogo');
    await client.query('DELETE FROM modelos_relatorio');
    await client.query('DELETE FROM sths');

    console.log('>> Inserindo STHs...');
    for (const s of STHS) {
      await client.query(
        `INSERT INTO sths (codigo, sop, sub_sop, descricao, status, criado_em)
         VALUES ($1, $2, $3, $4, $5, NOW())`,
        [s.codigo, s.sop, s.sub_sop, s.descricao, s.status]
      );
    }
    console.log(`   ${STHS.length} STHs inseridos.`);

    console.log('>> Inserindo linhas de tubulacao...');
    for (const l of LINHAS_TUBULACAO) {
      await client.query(
        `INSERT INTO linhas_tubulacao (numero_linha, tag, malha, sistema, sop, sub_sop, sth, pressao_teste, descricao_sistema, criado_em, atualizado_em)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())`,
        [l.numero_linha, l.tag, l.malha, l.sistema, l.sop, l.sub_sop, l.sth, l.pressao_teste, l.descricao_sistema]
      );
    }
    console.log(`   ${LINHAS_TUBULACAO.length} linhas inseridas.`);

    console.log('>> Inserindo modelos de relatorio...');
    for (const m of MODELOS_RELATORIO) {
      await client.query(
        `INSERT INTO modelos_relatorio (nome, descricao, tipo, caminho_template, campos, campos_template, ativo, data_criacao, criado_em, atualizado_em)
         VALUES ($1, $2, $3::tipomodelo, $4, $5::json, $6::json, $7, NOW(), NOW(), NOW())`,
        [m.nome, m.descricao, m.tipo, m.caminho_template, m.campos, m.campos_template, m.ativo]
      );
    }
    console.log(`   ${MODELOS_RELATORIO.length} modelos inseridos.`);

    await client.query('COMMIT');

    console.log('\n========================================');
    console.log('  SEED CONCLUIDO COM SUCESSO');
    console.log('========================================');

    const { rows: counts } = await client.query(`
      SELECT 'sths' AS tabela, COUNT(*)::int AS total FROM sths
      UNION ALL SELECT 'linhas_tubulacao', COUNT(*)::int FROM linhas_tubulacao
      UNION ALL SELECT 'modelos_relatorio', COUNT(*)::int FROM modelos_relatorio
    `);
    console.log('\nContagem final:');
    for (const r of counts) {
      console.log(`  ${r.tabela}: ${r.total} registros`);
    }

  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    console.error('\nERRO - Seed abortado (ROLLBACK executado):', err.message);
    console.error(err.detail || '');
  } finally {
    await client.end();
  }
}

seed();
