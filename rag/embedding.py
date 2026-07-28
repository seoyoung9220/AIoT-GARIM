import os
import requests

from dotenv import load_dotenv


# .env 파일 읽기
load_dotenv()

API_KEY = os.getenv("CLOVA_STUDIO_KEY")

MODEL_NAME = "clir-emb-dolphin"

URL = (
    "https://clovastudio.stream.ntruss.com"
    f"/v1/api-tools/embedding/{MODEL_NAME}"
)


# (연결 대기, 응답 대기) 초. 타임아웃이 없으면 API가 응답을 주지 않을 때
# 요청 스레드가 무한정 묶여서, 마스킹 항목 수만큼 스레드가 잠기면 서버 전체가 멈춘다.
# 연결은 짧게 끊어 서버가 아예 안 뜰 때 빨리 실패하게 하고, 응답은 넉넉히 준다.
TIMEOUT = (5, 30)


def get_embedding(text):

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "text": text
    }

    response = requests.post(
        URL,
        headers=headers,
        json=data,
        timeout=TIMEOUT
    )

    # 오류 발생 시 확인하기 쉽게 출력
    if response.status_code != 200:
        print("API 호출 실패")
        print("Status:", response.status_code)
        print("Response:", response.text)
        return None

    result = response.json()

    embedding = result["result"]["embedding"]

    return embedding


if __name__ == "__main__":

    text = "협력사 공유 시 전화번호는 부분 마스킹한다."

    embedding = get_embedding(text)

    if embedding is not None:

        print("Embedding 성공!")

        print("벡터 차원:", len(embedding))

        print("앞 10개 값:")
        print(embedding[:10])
