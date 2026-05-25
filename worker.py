import boto3, json, requests, time, logging
from datetime import datetime
from config import *

# Logs estruturados
logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    level=logging.INFO
)

sqs = boto3.client('sqs', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('moderation-results')

def load_prompt():
    with open('prompts/system_prompt_v1.txt') as f:
        return f.read()

def classify(text, retries=3):
    prompt_template = load_prompt()
    prompt = prompt_template.replace("{mensagem}", text)
    
    for attempt in range(retries):
        try:
            start = time.time()
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": "gemma2:2b", "prompt": prompt, "stream": False},
                timeout=30
            )
            latency = time.time() - start
            result = response.json()
            label = result['response'].strip().upper()
            tokens = result.get('eval_count', 0)
            return label, latency, tokens
        except Exception as e:
            wait = 2 ** attempt  # backoff exponencial
            logging.warning(f"Tentativa {attempt+1} falhou: {e}. Aguardando {wait}s")
            time.sleep(wait)
    return "ERRO", 0, 0

def process_messages():
    while True:
        response = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=5  # long polling
        )
        messages = response.get('Messages', [])
        
        for msg in messages:
            body = json.loads(msg['Body'])
            label, latency, tokens = classify(body['text'])
            
            # Salva no DynamoDB
            table.put_item(Item={
                'message_id': body['message_id'],
                'user_id': body['user_id'],
                'text': body['text'],
                'label': label,
                'latency_ms': int(latency * 1000),
                'tokens_used': tokens,
                'timestamp': int(body['timestamp']),
                'worker_id': open('/etc/hostname').read().strip()
            })
            
            logging.info(f"Classificado: {label} | latência: {latency:.2f}s | tokens: {tokens}")
            
            # Remove da fila apenas após sucesso
            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=msg['ReceiptHandle']
            )

if __name__ == '__main__':
    logging.info("Worker iniciado")
    process_messages()