"""rag/embedding.py — 외부 임베딩 API 호출의 타임아웃.

타임아웃이 없으면 CLOVA가 응답을 주지 않을 때 요청 스레드가 무한정 묶인다.
마스킹은 항목마다 임베딩을 부르므로, 스레드풀이 통째로 잠겨 서버가 멈춘다.
"""

import socket
import threading
import time

import pytest
import requests

from rag import embedding


def test_timeout_is_passed_to_requests(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("여기서 멈춘다 - 인자만 확인하면 된다")

    monkeypatch.setattr(embedding.requests, "post", fake_post)

    with pytest.raises(RuntimeError):
        embedding.get_embedding("테스트")

    assert captured.get("timeout") == embedding.TIMEOUT, \
        f"requests.post에 timeout이 전달되지 않음: {captured.keys()}"


@pytest.fixture
def dead_server():
    """연결은 받아주지만 응답을 절대 주지 않는 서버 (가장 고약한 장애 형태)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = sock.getsockname()[1]
    stop = threading.Event()
    held = []

    def accept_and_hang():
        sock.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
                held.append(conn)      # 받아두고 아무 응답도 하지 않는다
            except socket.timeout:
                continue
            except OSError:
                break

    thread = threading.Thread(target=accept_and_hang, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}/embedding"

    stop.set()
    thread.join(timeout=2)
    for conn in held:
        conn.close()
    sock.close()


def test_does_not_hang_forever(monkeypatch, dead_server):
    """응답 없는 서버를 만나도 정해진 시간 안에 포기해야 한다."""
    monkeypatch.setattr(embedding, "URL", dead_server)
    monkeypatch.setattr(embedding, "TIMEOUT", (1, 1))  # 테스트를 빠르게

    started = time.perf_counter()
    with pytest.raises(requests.exceptions.Timeout):
        embedding.get_embedding("테스트")
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"{elapsed:.1f}초나 걸림 - 타임아웃이 걸리지 않았다"


def test_default_timeout_is_bounded():
    """혹시 누가 None으로 되돌려도 테스트가 잡도록 값 자체를 확인한다."""
    connect, read = embedding.TIMEOUT

    assert connect and read, "타임아웃이 비활성화되어 있음"
    assert connect <= 10, f"연결 타임아웃이 너무 김: {connect}초"
    assert read <= 60, f"응답 타임아웃이 너무 김: {read}초"
