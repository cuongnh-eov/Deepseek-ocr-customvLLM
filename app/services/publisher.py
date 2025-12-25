# import pika
# import json

# def send_finished_notification(job_id):
#     # 1. Kết nối đến RabbitMQ
#     connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
#     channel = connection.channel()

#     # 2. Khai báo hàng đợi (Queue) tên là 'job_finished'
#     channel.queue_declare(queue='job_finished', durable=True)

#     # 3. Tạo nội dung tin nhắn dạng JSON
#     message = {
#         "job_id": job_id,
#         "status": "completed",
#         "timestamp": str(time.time())
#     }

#     # 4. Bắn tin nhắn (Publish)
#     channel.basic_publish(
#         exchange='',
#         routing_key='job_finished', # Tin nhắn gửi vào đúng "hòam thư" này
#         body=json.dumps(message)    # Chuyển dict thành chuỗi string để gửi đi
#     )
    
#     print(f"📢 Đã gửi tin nhắn thông báo Job {job_id} xong tới RabbitMQ")
#     connection.close()

import pika
import json
import time
import logging
from app.core.config import RABBIT_URL

logger = logging.getLogger(__name__)

def send_finished_notification(job_id: str):
    """
    Gửi thông báo hoàn tất Job tới hàng đợi 'job_finished'.
    Dùng để UI hoặc các service khác cập nhật trạng thái thời gian thực.
    """
    connection = None
    try:
        # 1. Kết nối đến RabbitMQ dùng URL từ config
        # Dùng pika.URLParameters để hỗ trợ cả amqp://user:pass@host:port/
        params = pika.URLParameters(RABBIT_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        # 2. Khai báo hàng đợi (Queue)
        channel.queue_declare(queue='job_finished', durable=True)

        # 3. Tạo nội dung tin nhắn
        message = {
            "job_id": job_id,
            "status": "completed",
            "finished_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "timestamp": time.time()
        }

        # 4. Publish tin nhắn với chế độ persistent (không mất khi restart RabbitMQ)
        channel.basic_publish(
            exchange='',
            routing_key='job_finished',
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        
        logger.info(f"📢 [NOTIFY] Đã báo hoàn tất Job {job_id}")

    except Exception as e:
        # Quan trọng: Không để lỗi gửi thông báo làm hỏng kết quả Job đã làm xong
        logger.error(f"⚠️ Không thể gửi thông báo hoàn tất cho Job {job_id}: {e}")
    
    finally:
        if connection and connection.is_open:
            connection.close()