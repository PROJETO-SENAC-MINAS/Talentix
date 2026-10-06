# Dezembro — ATS para empresas

## Instalação e acesso

Na raiz do Talentix, atualize a branch `arthur`. Com o ambiente virtual ativo,
execute `python migrate.py` dentro de `python/` e reinicie a API. A migration
`006_ats.sql` acrescenta nove tabelas, índices e chaves estrangeiras. O runner
registra checksum, usa lock de migration e não reaplica versões já instaladas.
O SQL de instalação limpa também inclui essas tabelas. Não execute o SQL completo
em um banco existente: use o runner incremental.

Empresa e recrutador: abra o painel habitual e clique em **ATS / Banco de talentos**.
A nova tela é `html/ats.html`. A empresa é resolvida pela sessão; um recrutador
precisa ter vínculo ativo com ela. Não é possível escolher outra empresa pela URL.

Administrador autorizado: o mesmo link existe no painel administrativo. Informe
explicitamente o ID da empresa no campo **ID da empresa para administração
autorizada** e clique em **Abrir empresa**. Também pode usar
`html/ats.html?empresa=ID_DA_EMPRESA`. Um administrador em modo usuário continua
limitado ao papel e vínculo desse modo.

As folhas de estilo anteriormente aprovadas foram preservadas. A nova tela usa
os mesmos cards, campos, botões, diálogos e sidebar, com CSS adicional exclusivo
para o grid do Kanban.

## Update 1 — Pipeline Visual / Kanban ATS

1. Abra **Pipeline** e selecione uma vaga. O sistema cria seis etapas iniciais
   somente quando ainda não existe configuração ativa: Novos, Triagem,
   Entrevista RH, Entrevista técnica, Proposta e Contratado.
2. A lista incorpora candidaturas existentes sem duplicar cards nem apagar o
   histórico anterior do processo. **Atualizar pipeline** incorpora novas entradas.
3. Arraste um card para outra coluna ou abra **Movimentar / detalhes**. Por teclado,
   use Tab para chegar ao botão, Enter para abrir, selecione o destino e salve.
4. No diálogo, configure responsável, prazo, posição (inicia em zero), status,
   observações internas e motivo. Reprovação e retirada exigem motivo. Aprovação
   é uma escolha explícita do RH; mover para uma coluna chamada Contratado não
   aprova automaticamente.
5. **Personalizar etapas** permite criar, renomear, reordenar e arquivar colunas.
   Uma coluna com candidatos ativos precisa ser esvaziada antes do arquivamento.
6. Os filtros de responsável/status atuam na vaga selecionada. Cada coluna mostra
   a quantidade encontrada. O diálogo conserva autor, ordem temporal, estado
   anterior/novo e anotações das movimentações.

Atualizações concorrentes usam versão do card. Uma versão desatualizada recebe
409 e pede recarregamento, sem sobrescrever a mudança de outro recrutador.
A posição inserida reorganiza a coluna de forma determinística. A mudança de
status pela tela antiga e a desistência do candidato também registram evento
no ATS. Candidaturas canceladas não podem ser reativadas pelo RH nessa tela.

## Update 2 — Scorecards e entrevistas estruturadas

1. Selecione a vaga em **Pipeline**, depois abra **Scorecards**.
2. Escolha uma etapa, dê nome à avaliação e adicione critérios. Cada critério tem
   peso positivo, nota de 0 a 5 e indicação de obrigatório/opcional.
3. Deixe marcado **Ocultar avaliações dos outros até enviar a minha** para
   avaliação cega. Essa proteção é aplicada pela API, inclusive no histórico do
   banco de talentos; esconder elementos no navegador não é a proteção.
4. Selecione um candidato e clique em **Avaliar candidato**, ou use **Ver
   scorecards** nos detalhes do card. Escolha o scorecard, preencha as notas,
   comentários, parecer final e recomendação **Aprovar / Avaliar / Reprovar**.
5. Cada integrante autorizado da empresa entra com sua própria conta e envia
   sua avaliação. Após enviar, pode consultar as avaliações liberadas, a média
   individual ponderada e a média dos entrevistadores.

Cada envio é imutável e identificado pelo entrevistador/data. Não é possível
substituir uma avaliação enviada; crie outro scorecard para uma nova rodada.
Critérios opcionais sem nota não entram no denominador. Ao menos uma nota é
necessária. A recomendação e as médias não mudam a candidatura: o RH toma a
 decisão no Pipeline.

## Update 3 — Talent CRM / Banco de talentos

**Autorização do candidato:** no painel do candidato, em Perfil, a seção
**Banco de talentos das empresas** lista empresas para as quais ele se candidatou.
Ele pode escolher **Autorizar banco de talentos** ou **Revogar autorização**.
A autorização começa desativada e não afeta a candidatura atual.

1. No ATS, abra **Banco de talentos** e **Gerenciar pools**. Crie pools como Backend,
   Frontend, Full Stack, Dados, QA, Jovem Aprendiz, Estágio ou Administrativo.
   Os nomes são configuráveis; também é possível renomear ou arquivar pools.
2. Pesquise por nome, habilidade, formação/curso, experiência/cargo e tag. Combine
   pool, favoritos e **Previamente avaliados**; a lista tem páginas de 20 resultados.
3. Abra **Histórico / pools / convite** de um talento. O histórico mostra somente
   os processos desta empresa, vagas anteriores, status, motivos de reprovação
   e scorecards liberados para a conta atual.
4. Escolha um pool, adicione tags, favorito e notas internas e salve. Use
   **Editar tags / notas** ou **Remover do pool** para ajustar os vínculos.
5. Escolha uma vaga publicada e **Enviar convite**. O candidato recebe uma
   notificação no painel e decide se quer se candidatar. O convite não cria
   candidatura automaticamente e não envia e-mail externo.

O banco requer simultaneamente relacionamento prévio com a empresa e
consentimento específico para ela. Autorizar a empresa A não autoriza B. Revogar
retira o candidato das buscas, impede novos convites e limpa tags/favoritos/notas
 dos pools dessa empresa. O histórico de candidaturas e avaliações fica preservado
para o processo anterior; não é exposto a outras empresas nem ao candidato como
notas internas.

## Update 4 — Consolidação e integração

- As rotas ATS exigem papel e autorização sobre empresa/vaga/candidatura/pool.
- Candidatos acessam somente suas próprias autorizações e dados públicos do
  processo. Notas de entrevistas internas também foram retiradas das respostas
  de candidatura/entrevistas destinadas ao candidato.
- As mutações usam CSRF e transações. Queries recebem parâmetros; IDs enviados
  para outro tenant não ampliam o escopo.
- O rate limit transversal inclui ATS e agrupa URLs por domínio de API, impedindo
  contornar o limite alternando IDs. Respostas ATS usam `Cache-Control: no-store`.
- Movimentações, avaliações, pools, convites e consentimentos têm auditoria.
- MySQL tem índices por vaga/etapa/empresa/candidato e unicidade de avaliação,
  convite e sequência do histórico.
- Testes HTTP cobrem IDOR, vínculos desativados, admin, CSRF, rate limit,
  notas obrigatórias, avaliação cega, isolamento do CRM, revogação, ordenação,
  conflitos e desistência. CI executa também MySQL real e Playwright E2E.
- Playwright verifica quatro larguras na interface ATS, drag-and-drop, alternativa
  por teclado, avaliações, pools e auditoria axe. Outro cenário usa API/MySQL reais
  para candidatura, consentimento, pipeline, avaliação, convite e revogação.

## Verificação

Com dependências instaladas, na raiz:

```text
python -m pytest python/tests -q
npm run test:ats --prefix web-tests
```

`npm test --prefix web-tests` inclui os fluxos reais e exige o ambiente descartável
`TALENTIX_ISOLATED_TESTS=1`. O GitHub Actions prepara MySQL 8, roda migrations duas
vezes, testes de API e ATS, navegador, acessibilidade e auditoria de dependências.
Não execute os scripts de integração num banco de uso cotidiano.
