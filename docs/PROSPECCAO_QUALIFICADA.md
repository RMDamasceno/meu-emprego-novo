# Prospecção qualificada: Cloud, DevOps, SRE e Helix

Esta extensão complementa o método original. A CLI com agentes continua responsável
pela adaptação do currículo. Este módulo adiciona triagem determinística, evidências,
regras comerciais e rastreamento. **Não busca vagas nem envia mensagens automaticamente.**

## 1. Princípios que vieram do método original

- Perfil-mestre como única fonte factual, acima de rascunhos anteriores.
- Currículo e apresentação específicos por oportunidade, sem competências inventadas.
- Verificação de cobertura e dos requisitos antes de investir na candidatura.
- Rastreamento por vaga, versão do currículo e comprovante.
- Retrospectivas periódicas para corrigir o processo.
- LinkedIn como vitrine coerente com o currículo, sem experiências fictícias.

A adaptação na CLI principal foi ajustada para começar sempre pelo JSON canônico:
currículos adaptados anteriormente não servem mais como fonte factual de outras vagas.

## 2. Melhorias específicas para a prospecção

1. **Buscar fontes oficiais:** anúncio vigente, cargo/código e página original.
   O anúncio precisa informar quando foi publicado; se faltar data, investigar.
2. **Triar e priorizar:** área, senioridade, local, modelo CLT/PJ, piso salarial,
   requisitos obrigatórios e diferenciais. A nota é heurística, nunca chance de contratação.
3. **Anexar evidência:** habilidade só conta quando existe no perfil profissional
   validado. Inglês fluente e certificações não são presumidos.
4. **Adaptar currículo:** escolher fatos relevantes sem alterar empregadores, datas,
   resultados ou atribuir ferramentas a cargos sem prova. Revisar o PDF antes de enviar.
5. **Verificar contatos:** confrontar endereço e demanda com publicação original e
   histórico de recebidos/enviados. Endereços que deram bounce ficam excluídos.
6. **Envio controlado:** sem CV anexável, confirmação do canal ou prova de destinatário,
   não enviar. Comprovante do envio e resposta/entrega são estados diferentes.
7. **Aprender:** medir candidaturas únicas, entrevistas, respostas por fonte e
   conversão das propostas comerciais. Revisar em ciclos quinzenais.

## 3. Dados privados e exemplos

O repositório público contém **somente dados fictícios** em
`examples/prospecting/`. Nunca salve currículo real, salários negociados,
nomes de recrutadores, e-mails, histórico de contatos ou PDFs no git.

Crie localmente:

```bash
mkdir -p privado input/vagas
cp examples/prospecting/policy.example.json privado/policy.json
cp examples/prospecting/profile.example.json privado/profile.json
cp examples/prospecting/job.example.json input/vagas/exemplo.json
```

Edite `privado/profile.json` com competências **comprovadas** pelo
`profile_truth.md`. A base `data/<pessoa>/resume.json` continua canônica
para o gerador de currículo. O JSON de triagem não substitui a base do currículo.

Configure `privado/policy.json` com pisos mensais **separados** para CLT
e PJ, levando em conta benefícios, impostos, férias e carga horária. O exemplo
mostra CLT R$ 12 mil e PJ R$ 18 mil **como ilustração**, não salário de mercado.

Valores de `mode`: `remote_br`, `hybrid_sp`; use `onsite` para registrar
uma vaga que será barrada pela política. Registre área, senioridade, contrato
e requisitos obrigatórios exatamente como publicados na fonte.

## 4. Operação local

```bash
# Vaga com evidência técnica, data e remuneração
python -m src.scripts.prospecting screen \
  --job input/vagas/exemplo.json \
  --profile privado/profile.json \
  --policy privado/policy.json \
  --tracker privado/tracker.jsonl

# Antes de encaminhar, valide os critérios efetivamente conferidos
python -m src.scripts.prospecting preflight \
  --job input/vagas/exemplo.json \
  --tracker privado/tracker.jsonl \
  --channel outlook --recipient recrutamento@exemplo.com \
  --source-verified --recipient-verified --history-checked \
  --screen-decision eligible \
  --attachment input/candidato/curriculo_atualizado.pdf

# APÓS confirmar o envio no provedor, registre o comprovante real
python -m src.scripts.prospecting record \
  --job input/vagas/exemplo.json \
  --tracker privado/tracker.jsonl \
  --status sent --receipt "outlook:<id-real>" \
  --attachment input/candidato/curriculo_atualizado.pdf \
  --source "Portal oficial"

# Atualizações posteriores: reply, interview, offer ou rejected
python -m src.scripts.prospecting record \
  --job input/vagas/exemplo.json \
  --tracker privado/tracker.jsonl \
  --status interview

python -m src.scripts.prospecting report --tracker privado/tracker.jsonl
```

Se houver falha de entrega, registre um evento `bounced` com `--recipient`
e mantenha esse endereço excluído de novos contatos.

O pré-envio retorna código 2 se houver bloqueios. A triagem também
retorna 2 para `review` ou `blocked`. A execução do módulo **não envia**
e-mails, não opera LinkedIn e não marca candidaturas como entregues.

Mesmo com pontuação 100, sem remuneração publicada ou fonte validada a triagem
retorna `review`. Faltas obrigatórias, inglês não comprovado, modalidade
incompatível ou envio anterior resultam em `blocked`.

## 5. B2B separado do processo pessoal

Registre cada objeto concreto, contratante, código de edital, link oficial,
requisitos de habilitação, prazo, custo/receita esperados e canal permitido.

- Licitação ou dispensa: proposta somente no sistema oficial, conforme edital.
- Workana/99Freelas e plataformas equivalentes: resposta dentro da plataforma.
- Demanda privada verificável: contato comercial individualizado, do Gmail
  profissional, depois de pesquisar o histórico e validar a empresa.
- Sem canal confirmado, escopo, destinatário ou histórico: não enviar.
- Contatos genéricos sem necessidade demonstrada não entram no funil.

Exemplo de verificação de proposta privada, após preencher `kind=b2b`,
`company`, `title` e `origin_type=private_company` em um arquivo local:

```bash
python -m src.scripts.prospecting preflight \
  --job input/vagas/proposta-privada.json \
  --channel gmail --recipient comercial@exemplo.com \
  --source-verified --recipient-verified \
  --history-checked --demand-verified
```

O preflight verifica condições informadas pelo operador, não pesquisa nem
atesta independentemente a identidade de quem publicou a vaga.

Para revisão do perfil profissional, use o prompt
[`prompts/11-linkedin-cloud-sre.md`](../prompts/11-linkedin-cloud-sre.md).
Ele gera propostas de título, Sobre, competências e auditoria de consistência
sem editar o LinkedIn ou publicar dados pessoais.

## 6. Indicadores e rotinas

| Frequência | Atividade | Indicadores |
|---|---|---|
| Diária | E-mails, status e devoluções | Envios confirmados e pendências |
| Diária | Novas vagas, fonte e requisitos | Vagas elegíveis por área |
| Diária | B2B com demanda específica | Propostas qualificadas e prazos |
| Quinzenal | Revisão de conversões | Entrevistas / candidaturas confirmadas |
| Quinzenal | Revisão de abordagem | Respostas B2B / propostas confirmadas |
| Mensal | Revisão do perfil e LinkedIn | Consistência do perfil, termos e retorno |

**Limitações:** a versão inicial usa correspondência exata das competências e
não interpreta sinônimos como AKS/Kubernetes. Inclua no perfil somente termos
que sua experiência realmente sustenta. Nota 100 não demonstra aprovação por
ATS. Não inclua dados pessoais em prompts de LLM sem revisar privacidade.

## 7. Validação sem chaves externas

```bash
python -m unittest tests.test_prospecting -v
```

Esses testes não usam tokens, bancos remotos, GitHub Actions nem provedor de IA.
Os testes do CrewAI seguem separados e dependem das respectivas bibliotecas.
