# Novembro — Updates 4, 5 e 6

Implementação na branch `arthur`, sem merge na `main`. API 1.2.0.

## Atualização de uma instalação

Faça backup do MySQL e do volume de uploads antes de atualizar. Não reimporte
`sql/talentix_db.sql` sobre um banco existente e não use `docker compose down -v`:
essa opção remove os volumes. Atualize a branch e execute:

```powershell
git switch arthur
git pull --ff-only
docker compose up --build --wait
```

O bootstrap aplica automaticamente a migration **005**, mantendo os registros
existentes. Ela adiciona campos profissionais, cursos/projetos, versões,
texto extraído, dados confirmados, buscas salvas, histórico e deduplicação dos
alertas. Currículos antigos recebem números de versão em ordem cronológica.
O usuário de execução continua sem CREATE/ALTER/GRANT. Nenhuma migration antiga
foi reescrita e o runner continua descobrindo migrations futuras.

O novo serviço `worker-profissional` compartilha o volume de arquivos com a API
e usa a conta restrita do banco. Não há novos segredos obrigatórios no `.env`.
Não usa serviços externos de IA. Sem Docker, execute `python migrate.py` com a
conta de migração e, em outro terminal, `python -m app.worker_profissional` com a
conta operacional. A API verifica o schema na inicialização, sem executar DDL.

## Update 4: perfil profissional

Na aba **Perfil**, todos os formulários profissionais ficam na mesma tela.
Experiências e formações também permanecem disponíveis pelas abas antigas.
Headline, apresentação, localização, disponibilidade, salário, modalidades,
contratos, links, preferências e habilidades comportamentais usam
`PUT /candidatos/{id}`. Experiências, formações, certificados, habilidades técnicas
e idiomas mantêm as APIs anteriores. Cursos e projetos usam:

| Método | Endpoint | Finalidade |
|---|---|---|
| GET | `/candidatos/{id}/profissional` | Perfil, coleções, completude e faltantes |
| POST | `/candidatos/{id}/itens` | Criar curso ou projeto |
| PUT / DELETE | `/itens-profissionais/{id}` | Editar/remover item próprio |
| PUT | `/candidatos/{id}/idiomas/{id_associacao}` | Editar idioma do próprio perfil |
| POST | `/uploads/foto-perfil` | Atualizar foto da conta autenticada |

Exemplo dos novos campos:

```json
{"modalidades":["remoto","hibrido"],"tipos_contrato":["CLT","PJ"],
 "habilidades_comportamentais":["Comunicação","Colaboração"],
 "preferencias":"Tecnologia, horário comercial"}
```

Contratos aceitos: `CLT`, `PJ`, `estagio`, `temporario`, `aprendiz`, `freelancer`.
As coleções têm limites; links aceitam apenas HTTP(S) sem credenciais. O backend
valida UF, datas, salário e comprimentos, além da validação HTML/JavaScript.

Completude é calculada dos dados oficiais, nunca enviada pelo cliente. Os pesos
somam 100: foto 5; headline 10; apresentação 10; cidade/UF 5; disponibilidade 2;
modalidades 5; salário 5; contratos 5; experiências 10; formação 10; certificados
3; cursos 3; projetos 5; habilidades técnicas 5; comportamentais 3; idiomas 3;
GitHub 5; LinkedIn 2; portfólio 2; preferências 2. Campos vazios não pontuam;
disponibilidade falsa e salário zero são respostas válidas. A interface consulta
o cálculo novamente depois de salvar, adicionar, editar ou remover dados.

**Visualizar perfil salvo** abre a prévia privada dos dados persistidos, com
experiências, preferências, formação, certificados, cursos, projetos, habilidades
e idiomas. Campos ainda não salvos não entram na prévia. Cursos ficam no card
**Formação acadêmica e cursos**, com inclusão/edição pelo formulário de estudos;
o card **Projetos** recebe somente projetos. Cursos anteriormente cadastrados
continuam disponíveis com seus mesmos IDs, descrições, links e datas, sem migração
nem exclusão. A prévia e o PDF seguem essa organização. As folhas de estilo são mantidas.

Foto: JPG/PNG/WebP, até o menor limite entre 5 MB e `MAX_UPLOAD_SIZE_MB`, até
16 megapixels. O servidor confere formato real, decodifica os pixels, remove
EXIF/ICC/metadados e grava PNG de até 1200×1200. SVG é recusado. Fotos não são
mais estáticas/públicas: exigem sessão e permissão sobre o perfil, com
`private, no-store`. Perfil do candidato só pode ser lido pelo proprietário,
admin ou empresa/recrutador com candidatura autorizada; não existe diretório
público de candidatos. Isso não é RLS nativo do MySQL: é autorização contextual
na API, com testes de IDOR.

## Update 5: currículo inteligente

Cada novo documento original cria uma versão imutável; upload idêntico reutiliza
o documento da mesma pessoa, sem sobrescrever o arquivo. A escrita física é
atômica e o nome deriva de SHA-256, nunca do nome fornecido pelo usuário.
O proprietário pode escolher o principal, mudar o título ou remover logicamente
uma versão. A exclusão não apaga os bytes compartilhados; versões não excluídas
continuam disponíveis e trocar o principal não altera candidaturas anteriores.

O botão **Histórico de versões** usa `GET /candidatos/{id}/curriculos/historico`
e inclui versões arquivadas, origem, número de versão e quantidade de candidaturas
com aquele documento. Somente proprietário/admin podem listar esse histórico.
**Editar nome** altera o título sem modificar os bytes nem o currículo principal.
Arquivar remove a versão do seletor de novas candidaturas; o proprietário pode
consultá-la no histórico e a empresa só pode acessar o documento anexado à sua
própria candidatura ativa. A primeira versão disponível torna-se principal; ao
arquivar a principal, a versão disponível mais recente assume essa preferência.
Prévia inline está disponível para PDF; DOC/DOCX são baixados.

| Método | Endpoint | Finalidade |
|---|---|---|
| POST / GET | `/candidatos/{id}/curriculos` | Upload e histórico de versões |
| PUT / DELETE | `/curriculos/{id}` | Título/principal ou remoção lógica |
| POST | `/curriculos/{id}/analisar` | Enfileirar análise ou retornar análise existente |
| GET | `/curriculos/{id}/importacao` | Consultar estado, texto e prévia privada |
| POST | `/curriculos/{id}/importacao/aplicar` | Aplicar somente dados aprovados |
| POST | `/candidatos/{id}/curriculo-talentix` | Gerar nova versão PDF a partir do perfil oficial |
| GET | `/uploads/curriculos/{hash}.pdf` | Download autorizado |
| GET | `/uploads/curriculos/{hash}.pdf?preview=true` | Prévia inline autorizada |

Estados persistidos: **1 aguardando**, **2 processando**, **3 concluída**, **4
falhou**. O worker reivindica itens com lock e retoma processamento abandonado
após dez minutos. Extração ocorre em subprocesso descartável, com timeout de
45 segundos e limites de CPU/memória no Linux; o subprocesso não recebe os
segredos/credenciais do banco da API. Texto tem limite de 100 mil
caracteres e PDF de 30 páginas. O processamento não ocupa a requisição de upload.
PDF digital e DOCX são analisados; DOC permanece apenas como arquivo legado.
PDF escaneado sem texto/OCR, criptografado ou ilegível resulta em erro orientativo,
sem expor caminhos ou mensagens internas. Não há promessa de extração perfeita.

`TextoExtraido`, `DadosExtraidos` e `DadosConfirmados` ficam separados do perfil.
Nome, e-mail e telefone são sugestões de contato; o e-mail autenticador não é
trocado pela importação, pois exige o fluxo de verificação da conta. Experiências,
formação/certificados, skills e idiomas também aparecem na prévia. Na interface,
as opções individuais começam **desmarcadas**. Confirmação explícita envia:

```json
{"selecionados":{"perfil":["resumo"],"experiencias":[0],"formacoes":[],
 "habilidades":[1],"idiomas":[]},"sobrescrever_perfil":false}
```

Índices referem-se à prévia armazenada no servidor. O cliente não pode injetar
dados oficiais substitutos. `sobrescrever_perfil=false` preserva campos já
preenchidos; sugestões inválidas são recusadas com orientação para desmarcar e
corrigir manualmente. Clientes anteriores ainda podem aprovar categorias inteiras
explicitamente omitindo `selecionados`; o worker nunca chama a confirmação.

A candidatura mantém a URL da versão selecionada. A empresa/recrutador só pode
baixar o currículo anexado à candidatura da própria empresa — não o acervo, o
texto extraído ou a prévia do candidato. Downloads/preview têm autorização,
`nosniff`, cache privado e sandbox. Não há montagem estática do diretório de CVs.
O PDF Talentix usa texto escapado; não incorpora imagens/URLs externas.

A revisão separa **Formação acadêmica**, **Certificados** e **Projetos**, cada
grupo com seleção independente. A extração v2 reconhece cabeçalhos de projetos
e não deixa suas descrições entrarem no grupo anterior. Formações e certificados
vão para `Formacoes` (certificados com `Nivel='Certificado'`); projetos vão para
`Candidato_Itens` com `Tipo='projeto'`. Repetir a confirmação não duplica os itens.
O cliente envia `versao_revisao: 2`, as seleções `certificados`/`projetos` e os
respectivos indicadores `importar_certificados`/`importar_projetos`. Seleções
continuam referenciando a prévia do servidor, nunca conteúdo enviado pelo cliente.
Análises v1 com texto armazenado recebem a nova separação ao abrir a revisão,
sem reenvio do arquivo e sem alterar o texto/original ou o perfil automaticamente.
Quando o texto antigo não está disponível, os certificados são separados pelo
nível já identificado; projetos antes não extraídos podem ser adicionados na seção Projetos.
Essa compatibilidade não reclassifica registros já confirmados no perfil.

A extração v3 também reconhece cabeçalhos compostos, como **EXPERIÊNCIA PRÁTICA ·
PRINCIPAIS PROJETOS PESSOAIS** e **CURSOS E CERTIFICAÇÕES COMPLEMENTARES**. Versões
anteriores (inclusive sem versão) com texto armazenado recebem a nova separação
ao reabrir a revisão. Anos em nomes de produtos, como Office 2016, não viram datas
de estudo. A interface verifica a versão recebida e orienta a atualizar/reiniciar
API e worker quando recebe uma revisão antiga, evitando enviar índices incompatíveis.
Erros de seleção distinguem categoria desconhecida, limite de 50 itens por grupo
e referências inválidas/desatualizadas; nenhum desses casos confirma dados parciais.

## Update 6: busca profissional

`GET /vagas/busca` é paginado, público e preserva `/vagas` como API legada da
listagem e gestão empresarial. Parâmetros: `cargo`, `palavra_chave`,
`localizacao`, `modalidade`, `salario_min`, `salario_max`, `nivel`,
`tipo_contrato`, `empresa`, `dias`, `habilidades` (até dez, separadas por vírgula),
`area`, `ordenar`, `pagina`, `por_pagina`. Limite: 50 resultados por página;
`ordenar` aceita apenas `relevancia`, `data` ou `salario`.

```text
/vagas/busca?cargo=python&localizacao=contagem&modalidade=remoto&pagina=1&por_pagina=20
/html/dashboard-candidato.html?cargo=python&localizacao=contagem&modalidade=Remoto
```

Resposta: `resultados`, `total`, `pagina`, `por_pagina`, `compatibilidade_base`.
Resultados incluem empresa pública, habilidades exigidas, compatibilidade e se
o candidato já se inscreveu. Compatibilidade mede correspondência entre skills e
níveis cadastrados, não probabilidade de contratação. Sem palavras de busca, a
relevância prioriza habilidades do perfil autenticado; com termos, prioriza
correspondência do título. Empates têm ordenação estável por data/ID.
Salários confidenciais são nulos, não são inferíveis pelo filtro ou ordenação.
Vagas rascunho/pausadas/encerradas e empresas inativas não são oportunidades.
Dados empresariais privados não são projetados nos resultados nem no catálogo
público de empresas. Consultas são parametrizadas; curingas LIKE do usuário são
escapados e cláusulas ORDER BY vêm de lista fixa.

`GET /vagas/autocomplete?q=py&limite=8` exige dois caracteres e limita a dez
sugestões. A interface usa debounce e lista nativa acessível. Filtros ficam na
URL ao recarregar; buscas/histórico são vinculados à sessão, não a IDs do cliente.
O número da página também é restaurado e ajustado se o total de vagas diminuir.
Também há detalhe, favoritar, compartilhar e seleção de CV na candidatura.

| Método | Endpoint | Finalidade |
|---|---|---|
| GET / POST | `/buscas` | Listar/criar busca própria (até 30) |
| PUT / DELETE | `/buscas/{id}` | Editar/pausar/excluir busca própria |
| GET / POST | `/buscas-historico` | Histórico limitado às últimas 20 pesquisas |

Busca salva recebe `nome`, `filtros` e `ativa`. O worker gera alertas somente para
buscas ativas e vagas publicadas depois da criação da busca. A chave única
`(ID_Busca,ID_Vagas)` impede repetição. Revalida publicação e estado da busca
dentro da transação. Notificação aparece no painel; e-mail é opcional, requer
SMTP configurado e conta com e-mail confirmado. Falha de SMTP não desfaz a
notificação; não existe garantia de entrega ou reenvio automático de e-mail.

## Segurança e verificações

Mantidos: hash bcrypt, sessão HttpOnly, CSRF para escritas, rate limit, validação,
CORS restrito, transações e autorização por proprietário/papel/contexto.
Não se adicionam credenciais ao Git nem permissões DDL à conta da API/worker.

Execute `python -m pytest tests -q` em `python`. No CI, `Security checks` também
executa bootstrap Compose, migrations repetidas, MySQL real, worker real,
`tests/mysql/run_november.py`, Playwright, Axe WCAG 2.2 A/AA, teclado/reflow e
auditoria de dependências. Relatórios são anexados à execução do Actions.
Axe não certifica conformidade WCAG completa: revisão humana de texto alternativo,
leitor de tela, foco e contrastes não textuais continua necessária.
