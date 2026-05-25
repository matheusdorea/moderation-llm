import boto3, json, uuid, time, random
from config import *

sqs = boto3.client('sqs', region_name='us-east-1')

mensagens_teste = [
    "Você é horrível e deveria desaparecer",
    "Ganhe dinheiro fácil clicando aqui!!!",
    "Alguém sabe que horas começa a aula?",
    "Seu trabalho é uma vergonha",
    "Promoção exclusiva só hoje, não perca!",
    "Obrigado pela ajuda de ontem",
]

for i in range(100):
    msg = random.choice(mensagens_teste)
    sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps({
            "message_id": str(uuid.uuid4()),
            "user_id": f"user_{random.randint(1,20)}",
            "text": msg,
            "timestamp": time.time()
        })
    )
    print(f"Enviada mensagem {i+1}")
    time.sleep(0.1)