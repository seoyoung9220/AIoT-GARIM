import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

from .prompts import (
    build_detection_prompt,
    build_policy_prompt,
)
from backend.app.schemas import (
    DetectedItem,
    MaskingPolicy,
    Target,
)


class ClovaClient:
    """
    CLOVA Studio HCX API Client
    """

    def __init__(self):
        self.url = (
            "https://clovastudio.stream.ntruss.com/"
            "v3/chat-completions/HCX-007"
        )

        self.session = requests.Session()

        self.headers = {
            "Authorization": f"Bearer {os.getenv('CLOVA_STUDIO_KEY')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _call(self, messages: list) -> dict:
        """
        HCX API 호출 후 JSON 응답 반환
        """

        payload = {
            "messages": messages,
            "thinking": {
                "effort": "none",
            },
            "topP": 0.8,
            "topK": 0,
            "temperature": 0.2,
            "maxCompletionTokens": 2048,
            "repetitionPenalty": 1.1,
        }

        response = self.session.post(
            self.url,
            headers=self.headers,
            json=payload,
            timeout=60,
        )

        response.raise_for_status()

        result = response.json()

        if result["status"]["code"] != "20000":
            raise RuntimeError(result)

        content = result["result"]["message"]["content"]

        if content.startswith("```json"):
            content = content[len("```json"):]
        elif content.startswith("```"):
            content = content[len("```"):]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        return json.loads(content)

    def detect_pii_llm(
        self,
        text: str,
    ) -> list[DetectedItem]:
        """
        OCR 텍스트에서
        이름 / 주소만 탐지한다.
        """

        messages = build_detection_prompt(text)

        result = self._call(messages)

        return [
            DetectedItem.model_validate(item)
            for item in result
        ]

    def decide_policy(
        self,
        target: Target,
        detected_item: DetectedItem,
        rag_results: dict,
    ) -> MaskingPolicy:
        """
        개인정보 1건에 대한
        마스킹 정책을 생성한다.
        """

        messages = build_policy_prompt(
            target=target,
            detected_item=detected_item,
            rag_results=rag_results,
        )

        result = self._call(messages)

        return MaskingPolicy.model_validate(result)