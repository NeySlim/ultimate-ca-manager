"""A 429 names the limit that refused the request, not another layer's."""
import json
import random


def test_login_429_carries_the_limit_that_was_hit(app):
    client = app.test_client()
    addr = f'8.8.{random.randint(1, 254)}.{random.randint(1, 254)}'
    responses = [client.post('/api/v2/auth/login/password', environ_base={'REMOTE_ADDR': addr},
                             content_type='application/json',
                             data=json.dumps({'username': 'nobody-rl', 'password': 'wrong'}))
                 for _ in range(6)]
    assert [r.status_code for r in responses[:5]] == [401] * 5
    refused = responses[5]
    assert refused.status_code == 429
    assert refused.headers['X-RateLimit-Limit'] == '5'
    assert refused.headers['X-RateLimit-Remaining'] == '0'
    assert int(refused.headers['Retry-After']) > 0
