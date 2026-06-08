# Moderação de Conteúdo Paralela em Tempo Quase Real

> **Disciplina:** Programação Distribuída e Paralela — CESUPA  
> **Tema 6** da atividade avaliativa de Harness Engineering aplicada a Sistemas Distribuídos  
> **Equipe:** Maheus Souza Dorea · João Victor Sousa Lira · Marcos Gama Bengtson

---

## Visão Geral

Sistema distribuído de moderação de conteúdo que classifica mensagens em tempo quase real usando um Small Language Model (SLM) auto-hospedado. Dois workers EC2 consomem uma fila SQS em paralelo, chamam o modelo Gemma 2B via Ollama e persistem os resultados no DynamoDB.

```
[ Producer ] ──→ [ SQS: moderation-queue ] ──→ [ DLQ: moderation-dlq ]
                          ↓               ↓
                    [ Worker 1 ]    [ Worker 2 ]
                          ↓               ↓
               [ Ollama API — EC2 t3.large / gemma2:2b ]
                               ↓
             [ DynamoDB: moderation-results ] ← [ Aggregator ]
```

---

## Estrutura do Repositório

```
moderation-llm/
├── producer.py          # Envia lote de mensagens para a fila SQS
├── worker.py            # Consome SQS, classifica via Ollama, grava DynamoDB
├── aggregator.py        # Lê DynamoDB e gera relatório de métricas
├── metrics.py           # Utilitários de coleta e formatação de métricas
├── config.py            # Variáveis de configuração (URLs, nomes de recursos)
├── requirements.txt     # Dependências Python
└── prompts/
    ├── system_prompt_v1.txt   # Classificador 3 categorias (TOXICO, SPAM, LIMPO)
    └── system_prompt_v2.txt   # Classificador 4 categorias (+ ASSEDIO)
```

---

## Pré-requisitos

- Conta AWS Academy ativa com permissões para EC2, SQS, DynamoDB e CloudWatch
- Python 3.10+
- Instância EC2 t3.large com Ollama instalado e modelo `gemma2:2b` baixado
- Duas instâncias EC2 t3.small para os workers com IAM Role `LabRole`

---

## Configuração

### 1. Recursos AWS

Crie os seguintes recursos na sua conta AWS Academy (região `us-east-1`):

**SQS — Fila principal:**
```
Nome:                  moderation-queue
Tipo:                  Standard
Visibility Timeout:    60 segundos
Dead Letter Queue:     moderation-dlq (maxReceiveCount = 3)
```

**SQS — Dead Letter Queue:**
```
Nome:                  moderation-dlq
Tipo:                  Standard
Retenção:              14 dias
```

**DynamoDB:**
```
Nome da tabela:        moderation-results
Partition Key:         message_id (String)
Capacidade:            On-demand
```

**CloudWatch Logs:**
```
Log Group:             /moderation/workers
```

### 2. Servidor Ollama (EC2 t3.large)

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Baixar modelo
ollama pull gemma2:2b

# Expor API na rede interna (para os workers acessarem)
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
```

> **Security Group:** libere a porta `11434` apenas para instâncias no mesmo Security Group dos workers. Não exponha publicamente.

### 3. Workers (EC2 t3.small × 2)

```bash
# Em cada instância worker
sudo apt update && sudo apt install python3-pip -y
git clone https://github.com/<seu-usuario>/moderation-llm.git
cd moderation-llm
pip3 install -r requirements.txt
```

### 4. Configuração (`config.py`)

Edite `config.py` com os valores reais da sua conta:

```python
OLLAMA_URL     = "http://<IP-PRIVADO-EC2-OLLAMA>:11434"
SQS_QUEUE_URL  = "https://sqs.us-east-1.amazonaws.com/<ACCOUNT-ID>/moderation-queue"
DYNAMODB_TABLE = "moderation-results"
AWS_REGION     = "us-east-1"
```

---

## Execução

### Passo 1 — Enviar mensagens para a fila

Execute no seu ambiente local ou em qualquer instância com credenciais AWS:

```bash
python3 producer.py
```

O producer envia 100 mensagens simuladas para `moderation-queue`.

### Passo 2 — Iniciar os dois workers (em paralelo)

Em cada instância worker, abra um terminal e execute:

```bash
python3 worker.py
```

Os workers ficam em loop contínuo consumindo a fila. Para parar: `Ctrl+C`.

### Passo 3 — Gerar relatório de métricas

Após o processamento, execute o aggregator em qualquer instância:

```bash
python3 aggregator.py
```

O aggregator lê o DynamoDB e imprime um relatório com contadores por categoria, latência média e tokens consumidos.

---

## System Prompts

Os prompts estão versionados no diretório `prompts/` e são carregados pelo worker em tempo de execução. Alterações na estratégia de classificação não requerem modificação do código de infraestrutura.

| Versão | Categorias | Few-shot Examples | Tokens aprox. |
|--------|-----------|-------------------|---------------|
| v1 | TOXICO, SPAM, LIMPO | 6 (2 por categoria) | ~120 |
| v2 | TOXICO, SPAM, LIMPO, ASSEDIO | 8 (2 por categoria) | ~160 |

Para alternar entre versões, edite a variável `PROMPT_VERSION` em `config.py`.

---

## Tolerância a Falhas

| Mecanismo | Comportamento |
|-----------|--------------|
| Retry com backoff exponencial | 3 tentativas, espera 2^n segundos (1s, 2s, 4s) |
| Dead Letter Queue | Mensagens com 3 falhas de entrega são redirecionadas |
| Fallback de classificação | Retorna label `ERRO` após esgotar retries |
| Visibility timeout | 60s — mensagem retorna à fila se o worker crashar |
| DynamoDB On-demand | Sem throttling configurado; boto3 retenta automaticamente |

---

## Métricas Coletadas

- Latência por requisição (ms)
- Total de tokens consumidos
- Throughput por worker
- Distribuição de classificações por categoria
- Identificação do worker responsável por cada mensagem (`worker_id`)

Logs estruturados em formato JSON são enviados ao CloudWatch Logs (`/moderation/workers`).

---

## Infraestrutura AWS Utilizada

| Serviço | Configuração | Papel |
|---------|-------------|-------|
| EC2 t3.large | Ubuntu 22.04, Ollama + gemma2:2b | Servidor de inferência SLM |
| EC2 t3.small × 2 | Ubuntu 22.04, IAM Role: LabRole | Workers Python |
| Amazon SQS | Standard, visibilityTimeout=60s | Fila principal |
| Amazon SQS DLQ | Standard, retenção 14 dias | Mensagens com falha |
| Amazon DynamoDB | On-demand, PK: message_id | Persistência de resultados |
| Amazon CloudWatch | Log Group JSON estruturado | Observabilidade |

---

## Resultados Experimentais (carga de 155 mensagens)

| Métrica | Valor |
|---------|-------|
| Latência média global | 1.226 ms |
| Latência média (warm, excl. erros) | 5.174 ms |
| Cold start observado | 19.100 ms |
| Tokens por resposta | 5 tokens |
| Workers paralelos | 2 instâncias EC2 |
| Throughput (warm) | ~0,4 req/s por worker |

> A alta taxa de erro (84,5%) nos testes reflete o timeout de 30s configurado abaixo da latência de cold start do Gemma 2B em CPU. Aumente o timeout para ≥ 60s ou implemente um warmup request na inicialização do worker para eliminar esse comportamento.

---

## Declaração de Uso de IA Generativa

Ferramentas de IA foram utilizadas como suporte em: refatoração de código, formatação do documento técnico e revisão textual do README. Todo o raciocínio arquitetural, decisões de design e análise experimental são de autoria da equipe.
