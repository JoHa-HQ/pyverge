from typing import TypeAlias

from faststream import kafka, nats, rabbit, redis

Broker: TypeAlias = (
    redis.RedisBroker | kafka.KafkaBroker | nats.NatsBroker | rabbit.RabbitBroker
)
