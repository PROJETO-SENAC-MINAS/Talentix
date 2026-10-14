# Revisão de segurança — 14/10/2026

Escopo: diferença da branch `arthur` a partir de `3fbc14c`, módulos legados afetados,
frontend, migração 007, worker e operação local. Revisão manual de fonte e testes,
com Bandit e auditorias de dependências. Não constitui pentest independente ou certificação.
O workflow completo do plugin Codex Security não foi executado: suas referências complementares
não estavam disponíveis no ambiente. Não há relatório fictício desse serviço.

## Controles verificados

| Risco | Controle/evidência |
|---|---|
| IDOR/BOLA entre pessoas e empresas | ACL compartilhada, sessão revalidada, contexto empresarial não confiável, testes A/B/MySQL |
| Escalada e revogação | Roles no banco, revogação prevalece sobre legado, último Owner protegido, convites vinculados a e-mail confirmado |
| CSRF/sessões | Cookie HttpOnly/SameSite, Secure em produção, token CSRF/origem nas mutações, revogação persistida |
| SQLi/mass assignment | Valores parametrizados, modelos com limites, mapas literais para nomes de coluna; revisão de cada alerta B608 |
| XSS/injeção em exportação | HTML/texto escapados, JSON-LD neutraliza delimitadores, CSV neutraliza fórmulas, PDF escapa texto |
| SSRF | Push restrito a provedores de navegador, HTTPS, DNS público e redirects desativados; sem URL arbitrária de callback |
| Upload/leitura privada | PDF validado, armazenamento separado e autorização por processo, sem publicação estática |
| Concorrência/repetição | Transações, locks atuais, versões e chaves de repetição; cenário concorrente no MySQL padrão |
| Abuso | Buckets sensíveis, tamanho de request/upload, até 100 destinatários e dez lotes/dia, preferência explícita |
| Vazamento por cache/log | API privada no-store, SW só público, logs SMTP genéricos, frontend não registra queries com tokens |
| Efeito externo antes do commit | SMTP por outbox; claim/lease fora da transação de negócio, retentativa limitada |
| IA decisória | Somente cálculo local/orientação; nenhuma publicação, contratação, reprovação ou edição autônoma |

## SAST e dependências

`python python/check_sast.py` executa Bandit 1.9.4 em `python/app` e grava relatório completo
em `test-results/bandit.json`. A revisão inicial contém 30 alertas B608 de severidade média,
com confiança baixa/média, por SQL construído com mapas/tuplas literais ou placeholders.
Cada aceitação em `security/bandit-reviewed.json` contém justificativa, linha, tipo, severidade,
confiança e SHA-256 do arquivo inteiro. Qualquer mudança no arquivo exige nova análise;
alerta novo ou alto falha no CI. Nenhuma regra foi desativada e o relatório mantém os alertas.
A revisão reduz falsos positivos conhecidos, não prova ausência de vulnerabilidade.

`pip-audit` cobre requirements-dev (inclui runtime e IA); `npm audit` cobre o lock de testes.
Auditorias verificam vulnerabilidades publicadas, sem avaliar integralmente a cadeia de suprimentos.
Versões/ferramentas devem ser atualizadas com revalidação. Relatórios e dados fictícios de teste
permanecem em artefatos do CI, sem currículos ou segredos reais.

## Limites e pendências de produção

- README mantém a exposição histórica de credenciais: rotação no provedor e limpeza coordenada
  do histórico dependem dos responsáveis. Não houve reescrita de histórico nem uso de segredo antigo.
- Rate limit é por processo; múltiplas réplicas precisam de limite compartilhado no proxy/Redis.
- Entrega SMTP/push é ao menos uma vez. Interrupção após aceite do provedor pode repetir aviso.
- Homologar SMTP/push reais, backups/restore, disponibilidade, carga sustentada, HTTPS e domínios reais.
- Fazer revisão humana de acessibilidade, privacidade e retenção, e testes específicos de perfil Entrevistador.
- Texto livre pode conter PII; o índice local não tem certificação de viés ou qualidade semântica.
- Permissões administrativas existentes continuam sensíveis e auditadas; não ampliá-las para integrações genéricas.

Esses limites constam também da agenda; não se declara RC/produção ou conformidade integral por testes automáticos.
