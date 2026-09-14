import dramatiq
from dramatiq.brokers.redis import RedisBroker

redis_broker = RedisBroker(url="redis://localhost:6379/0")
dramatiq.set_broker(redis_broker)


@dramatiq.actor
def no_op_task():
    print("Worker is ready and running")
