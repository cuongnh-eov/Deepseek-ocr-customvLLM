"""
app/queue.py
- Vai trò: API đẩy message vào RabbitMQ.
- Message tối thiểu chỉ cần {"job_id": "..."} vì mọi thứ khác nằm trong DB.
"""

import os
import json
import pika # Thư viện RabbitMQ client

RABBIT_URL = os.getenv('RABBIT_URL', 'amqp://guest:guest@localhost:5672/')
QUEUE_NAME = os.getenv("QUEUE_NAME", "ocr_jobs")

def publish_job(message:dict)->None:
    """Đẩy message job vào RabbitMQ."""
    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    # durable=True: queue tồn tại qua restart RabbitMQ (nếu cấu hình persistence
    ch.queue_declare(queue=QUEUE_NAME, durable=True)

    ch.basic_publish(
        exchange='',
        routing_key=QUEUE_NAME,
        body=json.dumps(message).encode('utf-8'),
        properties=pika.BasicProperties(
            delivery_mode=2,  # Make message persistent
        )
    )

    # print(f" [x] Published job: {message}")

    conn.close()