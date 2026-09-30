# Fluxo inicial e regras da apresentação

O diagrama é conceitual: os métodos indicam responsabilidades de negócio. A API implementa essas responsabilidades em funções FastAPI com schemas Pydantic e SQL, sem ORM. Dashboard é um serviço de métricas, não uma tabela. A estrutura tem 37 tabelas de aplicação (29 de negócio e oito domínios); `Schema_Migrations` registra as atualizações de uma instalação existente.

A empresa possui histórico de assinaturas, com **no máximo uma ativa**. O banco impõe essa unicidade, a unicidade da transação de pagamento e uma avaliação por avaliador/candidatura. Uma candidatura e sua primeira etapa são confirmadas na mesma transação. Leituras isoladas usam autocommit, sem alterar o isolamento padrão do MySQL.

| Papel | Acesso inicial | Limites |
|---|---|---|
| Candidato | Perfil, documentos, vagas, candidaturas, entrevistas, comunicação e desenvolvimento | Dados próprios; só se candidata a vagas publicadas de empresas ativas |
| Empresa | Perfil da empresa, vagas, candidatos inscritos, etapas, entrevistas e equipe | Acesso apenas à empresa responsável e ao currículo anexado à candidatura |
| Recrutador | Vagas e processos da empresa de seu vínculo ativo | Não verifica empresas, administra equipe ou financeiro; revogação do vínculo remove o acesso imediatamente |
| Administrador | Métricas, verificação, denúncias, cursos, idiomas e contatos | Operações administrativas exigem perfil ativo |
| Recrutador sem vínculo | Painel de espera com seu ID | O responsável da empresa deve conceder o vínculo |

## Ensaio no navegador

1. Prepare MySQL e a configuração local. Para banco existente, execute a migração; não reimporte o SQL de instalação.
2. Crie o administrador pelo comando documentado no README e cadastre cursos de preparação no painel administrativo.
3. Cadastre uma empresa e um recrutador pela tela de login. No painel da empresa, adicione o ID mostrado no painel de espera do recrutador; ele verifica o vínculo e entra no seu painel.
4. Crie e publique uma vaga. Informe as habilidades obrigatórias no formulário da vaga.
5. Cadastre um candidato, preencha o perfil e envie um currículo fictício. Busque a vaga, escolha o documento no formulário da candidatura e envie.
6. Na empresa, abra a candidatura e o documento anexado, adicione etapas e agende a entrevista com um recrutador da própria empresa.
7. No candidato, acompanhe o status, a entrevista e as notificações. Troque mensagens pelo contexto da candidatura.
8. Solicite a compatibilidade no acompanhamento. Com o worker em execução, veja pontuação, pontos fortes, lacunas e cursos pertinentes na aba Desenvolvimento.
9. Envie um contato e consulte-o no painel administrativo. Demonstre a verificação de empresa, o catálogo e a resolução de uma denúncia fictícia.

## Compatibilidade e integrações

O worker incluído calcula um índice local com TF-IDF e habilidades declaradas; não é um modelo generativo nem uma previsão de contratação. Havendo habilidades exigidas, o peso é 80% para habilidades (respeitando nível, peso e obrigatoriedade) e 20% para similaridade textual. Sem habilidades exigidas, utiliza apenas a similaridade dos textos. Nome, e-mail, cidade, salário e outros dados pessoais não entram no cálculo. O texto vem do perfil, experiências e formações; o conteúdo de PDF/DOC não é extraído. O modelo e a justificativa ficam registrados junto ao resultado.

A fila segue NA_FILA → PROCESSANDO → CONCLUIDO/FALHOU, com recuperação de trabalhos interrompidos após dez minutos e bloqueio para evitar que dois workers assumam o mesmo registro. Cursos ativos são sugeridos quando sua descrição/categoria/título contêm uma habilidade ausente. Isso auxilia a preparação; a decisão do processo continua com a empresa. Referência do algoritmo: [documentação do scikit-learn](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction).

SMTP exige as credenciais reais do provedor, configuradas localmente. Com SMTP desativado, as notificações continuam funcionando no site; recuperação de senha não entrega e-mail. Os testes não enviam mensagens externas.

Os endpoints financeiros registram assinaturas, pagamentos e resultados autenticados. O callback é idempotente e não altera um pagamento terminal para outro resultado. **Não há checkout nem devolução de dinheiro real**: o gateway contratado deve validar sua assinatura de webhook e executar cobrança/devolução antes de registrar o resultado interno. Essa integração depende do provedor e será uma etapa separada.
