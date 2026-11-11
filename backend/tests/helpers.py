CAPTCHA_ANSWER = 'K7M9Q'

def register(client, username='test_user', password='secure-test-pass'):
    challenge = client.get('/api/v1/auth/captcha')
    assert challenge.status_code == 200
    return client.post('/api/v1/auth/register', json={
        'username': username, 'password': password,
        'captcha_id': challenge.json()['id'], 'captcha_answer': CAPTCHA_ANSWER,
    })
