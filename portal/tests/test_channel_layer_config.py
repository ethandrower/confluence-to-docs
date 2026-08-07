"""The Redis channel layer's client read timeout must outlast its own blocking read.

Production incident, 2026-08-07: WebSocket connections dropped every few
minutes with `redis.exceptions.TimeoutError: Timeout reading from ...`, logged
as "Exception in ASGI application".

Cause: channels_redis's receive loop issues `bzpopmin(channel, timeout=5)` —
a blocking read that waits up to `brpop_timeout` (5s) for a message. redis-py
8.0 introduced `DEFAULT_SOCKET_TIMEOUT = 5`, applying a *client-side* 5s read
timeout by default where 7.x had none. Two 5-second timers racing: when a
quiet channel makes the server take the full 5s, the client's timeout can fire
first, and because nothing passes an explicit `timeout` to `read_response`,
redis-py takes the branch that disconnects the socket and raises.

requirements.txt pinned `redis>=5.0`, so a rebuild silently moved production
from 7.4.0 to 8.0.1 and the default changed underneath us.

This test encodes the invariant rather than the version: whatever redis-py
does by default, our configured client timeout must exceed the blocking read
it wraps.
"""
from django.conf import settings
from django.test import TestCase


class ChannelLayerTimeoutTest(TestCase):
    def _configured_hosts(self):
        cfg = settings.CHANNEL_LAYERS.get('default', {})
        return (cfg.get('CONFIG') or {}).get('hosts') or []

    def test_socket_timeout_outlasts_the_blocking_read(self):
        from channels_redis.core import RedisChannelLayer
        from channels_redis.utils import create_pool, decode_hosts

        hosts = self._configured_hosts()
        if not hosts:
            self.skipTest('in-memory channel layer (no REDIS_URL configured)')

        blocking = RedisChannelLayer.brpop_timeout
        for host in decode_hosts(hosts):
            socket_timeout = create_pool(host).connection_kwargs.get('socket_timeout')
            self.assertIsNotNone(
                socket_timeout,
                'No socket_timeout configured — redis-py 8+ defaults it to 5s, '
                'which ties with brpop_timeout and drops WebSocket connections.')
            self.assertGreater(
                socket_timeout, blocking,
                f'socket_timeout ({socket_timeout}s) must exceed '
                f'brpop_timeout ({blocking}s), or the client can time out on '
                f'its own blocking read and drop the connection.')
