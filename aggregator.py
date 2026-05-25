import boto3
from collections import Counter

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('moderation-results')

items = table.scan()['Items']

labels = Counter(i['label'] for i in items)
por_usuario = Counter(i['user_id'] for i in items if i['label'] == 'TOXICO')
latencias = [int(i['latency_ms']) for i in items if 'latency_ms' in i]
tokens = [int(i['tokens_used']) for i in items if 'tokens_used' in i]

print("=== RELATÓRIO DE MODERAÇÃO ===")
print(f"Total processado: {len(items)}")
print(f"Distribuição: {dict(labels)}")
print(f"Top usuários tóxicos: {por_usuario.most_common(5)}")
print(f"Latência média: {sum(latencias)/len(latencias):.0f}ms")
print(f"Total tokens consumidos: {sum(tokens)}")