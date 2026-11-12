import time
from fastapi.testclient import TestClient
from app import main
from .e2e_server import ScenarioApp


def test_production_limit_remains_and_reset_is_test_only(anon):
    main.limits['testclient'].extend([time.monotonic()]*180)
    assert anon.get('/api/v1/healthz').status_code==429
    assert anon.post('/__test/reset-rate-limits').status_code==429
    with TestClient(ScenarioApp()) as test_server:
        assert test_server.post('/__test/reset-rate-limits').status_code==204
        assert test_server.get('/api/v1/healthz').status_code==200
    assert anon.post('/__test/reset-rate-limits').status_code==404
