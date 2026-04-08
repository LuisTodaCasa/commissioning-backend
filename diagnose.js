const { Client } = require('pg');

const client = new Client({
  connectionString: process.env.DATABASE_URL,
  ssl: {
    rejectUnauthorized: false
  }
});

const SEPARATOR = '='.repeat(60);
const SUB_SEPARATOR = '-'.repeat(40);

async function run() {
  try {
    await client.connect();
    console.log(SEPARATOR);
    console.log('  DIAGNOSTICO DO BANCO DE DADOS');
    console.log(SEPARATOR);

    const { rows: connTest } = await client.query('SELECT NOW() AS hora, current_database() AS banco, current_user AS usuario, version() AS versao');
    console.log('\n>> Conexao OK');
    console.log(`   Banco: ${connTest[0].banco}`);
    console.log(`   Usuario: ${connTest[0].usuario}`);
    console.log(`   Hora do servidor: ${connTest[0].hora}`);
    console.log(`   Versao: ${connTest[0].versao}`);

    console.log(`\n${SEPARATOR}`);
    console.log('  1. TABELAS EXISTENTES');
    console.log(SEPARATOR);

    const { rows: tables } = await client.query(`
      SELECT t.table_name,
             pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))) AS tamanho,
             s.n_live_tup AS registros_aprox
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
      ORDER BY t.table_name
    `);

    if (tables.length === 0) {
      console.log('\n  NENHUMA TABELA ENCONTRADA no schema public.');
      console.log('  Verifique se o DATABASE_URL aponta para o banco correto.');
    } else {
      console.log(`\n  Total: ${tables.length} tabela(s)\n`);
      const maxName = Math.max(...tables.map(t => t.table_name.length), 6);
      console.log(`  ${'TABELA'.padEnd(maxName)}  ${'REGISTROS'.padStart(10)}  TAMANHO`);
      console.log(`  ${'-'.repeat(maxName)}  ${'-'.repeat(10)}  -------`);
      for (const t of tables) {
        console.log(`  ${t.table_name.padEnd(maxName)}  ${String(t.registros_aprox ?? '?').padStart(10)}  ${t.tamanho}`);
      }
    }

    console.log(`\n${SEPARATOR}`);
    console.log('  2. TABELAS VAZIAS');
    console.log(SEPARATOR);

    const empty = tables.filter(t => Number(t.registros_aprox) === 0);
    if (empty.length === 0) {
      console.log('\n  Nenhuma tabela vazia encontrada.');
    } else {
      console.log(`\n  ${empty.length} tabela(s) vazia(s):\n`);
      for (const t of empty) {
        console.log(`  - ${t.table_name}`);
      }
    }

    console.log(`\n${SEPARATOR}`);
    console.log('  3. AMOSTRA DE DADOS (5 registros por tabela)');
    console.log(SEPARATOR);

    for (const t of tables) {
      const tableName = t.table_name;
      console.log(`\n${SUB_SEPARATOR}`);
      console.log(`>> ${tableName}`);
      console.log(SUB_SEPARATOR);

      try {
        const { rows: cols } = await client.query(`
          SELECT column_name, data_type, is_nullable, column_default
          FROM information_schema.columns
          WHERE table_name = $1 AND table_schema = 'public'
          ORDER BY ordinal_position
        `, [tableName]);

        console.log(`   Colunas: ${cols.map(c => `${c.column_name} (${c.data_type}${c.is_nullable === 'YES' ? ', null' : ''})`).join(', ')}`);

        const { rows: sample } = await client.query(`SELECT * FROM "${tableName}" LIMIT 5`);
        if (sample.length === 0) {
          console.log('   [VAZIA]');
        } else {
          console.table(sample);
        }
      } catch (err) {
        console.log(`   ERRO ao ler tabela: ${err.message}`);
      }
    }

    console.log(`\n${SEPARATOR}`);
    console.log('  4. ANALISE DE INCONSISTENCIAS');
    console.log(SEPARATOR);

    let issues = 0;

    const { rows: noId } = await client.query(`
      SELECT t.table_name
      FROM information_schema.tables t
      WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        AND NOT EXISTS (
          SELECT 1 FROM information_schema.table_constraints tc
          WHERE tc.table_name = t.table_name
            AND tc.table_schema = 'public'
            AND tc.constraint_type = 'PRIMARY KEY'
        )
    `);
    if (noId.length > 0) {
      issues += noId.length;
      console.log(`\n  [ALERTA] Tabelas SEM PRIMARY KEY:`);
      for (const t of noId) console.log(`    - ${t.table_name}`);
    }

    const { rows: fks } = await client.query(`
      SELECT
        tc.table_name AS tabela_origem,
        kcu.column_name AS coluna_fk,
        ccu.table_name AS tabela_destino,
        ccu.column_name AS coluna_destino
      FROM information_schema.table_constraints tc
      JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
      JOIN information_schema.constraint_column_usage ccu
        ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
      WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    `);

    if (fks.length > 0) {
      console.log(`\n  Foreign Keys encontradas:`);
      for (const fk of fks) {
        console.log(`    ${fk.tabela_origem}.${fk.coluna_fk} -> ${fk.tabela_destino}.${fk.coluna_destino}`);
      }

      for (const fk of fks) {
        try {
          const { rows: orphans } = await client.query(`
            SELECT COUNT(*) AS total FROM "${fk.tabela_origem}" o
            LEFT JOIN "${fk.tabela_destino}" d ON o."${fk.coluna_fk}" = d."${fk.coluna_destino}"
            WHERE o."${fk.coluna_fk}" IS NOT NULL AND d."${fk.coluna_destino}" IS NULL
          `);
          if (Number(orphans[0].total) > 0) {
            issues++;
            console.log(`\n  [ERRO] ${orphans[0].total} registro(s) orfao(s): ${fk.tabela_origem}.${fk.coluna_fk} referencia ${fk.tabela_destino} inexistente`);
          }
        } catch (err) {
          console.log(`  [AVISO] Nao foi possivel checar orfaos em ${fk.tabela_origem}: ${err.message}`);
        }
      }
    }

    const { rows: nullableCols } = await client.query(`
      SELECT table_name, column_name
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND is_nullable = 'YES'
        AND (column_name LIKE '%name%' OR column_name LIKE '%email%' OR column_name LIKE '%title%' OR column_name LIKE '%nome%' OR column_name LIKE '%titulo%')
    `);
    if (nullableCols.length > 0) {
      issues += nullableCols.length;
      console.log(`\n  [AVISO] Colunas importantes que aceitam NULL:`);
      for (const c of nullableCols) {
        console.log(`    - ${c.table_name}.${c.column_name}`);
      }
    }

    for (const t of tables) {
      try {
        const { rows: nullCounts } = await client.query(`
          SELECT column_name, COUNT(*) AS total_nulls
          FROM information_schema.columns c
          CROSS JOIN LATERAL (
            SELECT 1 FROM "${t.table_name}" WHERE "${t.table_name}"."${t.table_name}" IS NULL
          ) sub
          WHERE c.table_name = $1 AND c.table_schema = 'public'
          GROUP BY column_name
        `, [t.table_name]);
      } catch (err) {
      }
    }

    const { rows: dupIndexes } = await client.query(`
      SELECT tablename, array_agg(indexname) AS indices, indexdef
      FROM pg_indexes
      WHERE schemaname = 'public'
      GROUP BY tablename, indexdef
      HAVING COUNT(*) > 1
    `);
    if (dupIndexes.length > 0) {
      issues += dupIndexes.length;
      console.log(`\n  [AVISO] Indices duplicados:`);
      for (const d of dupIndexes) {
        console.log(`    Tabela ${d.tablename}: ${d.indices.join(', ')}`);
      }
    }

    const { rows: seqCheck } = await client.query(`
      SELECT sequencename, last_value
      FROM pg_sequences
      WHERE schemaname = 'public'
    `);
    if (seqCheck.length > 0) {
      console.log(`\n  Sequences encontradas:`);
      for (const s of seqCheck) {
        console.log(`    ${s.sequencename} -> ultimo valor: ${s.last_value ?? 'nao inicializada'}`);
      }
    }

    console.log(`\n${SEPARATOR}`);
    if (issues === 0) {
      console.log('  RESULTADO: Nenhuma inconsistencia detectada.');
    } else {
      console.log(`  RESULTADO: ${issues} possivel(eis) inconsistencia(s) encontrada(s).`);
    }
    console.log(SEPARATOR);

  } catch (err) {
    console.error('Erro ao conectar no banco:', err.message);
    console.error('Verifique se DATABASE_URL esta definida corretamente.');
  } finally {
    await client.end();
  }
}

run();
