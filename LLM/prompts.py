from backend.app.schemas import DetectedItem, Target


SYSTEM_DETECTION = """
당신은 계약서 개인정보 탐지 전문가입니다.

다음 규칙을 반드시 지키세요.

1. 이름(name)과 주소(address)만 탐지합니다.
2. 전화번호, 주민등록번호, 사업자등록번호, 계좌번호는 무시합니다.
3. OCR 오류를 고려하여 의미를 판단합니다.
4. 반드시 JSON 배열만 출력합니다.
5. 설명, 주석, 서론, 결론은 절대 출력하지 않습니다.
6. Markdown 코드블록(``` 또는 ```json)을 절대 사용하지 않습니다.
7. JSON 이외의 어떠한 문자도 출력하지 않습니다.

출력 형식:

[
  {
    "id": "...",
    "type": "name",
    "value": "...",
    "page": 1,
    "bbox": [],
    "source": "llm"
  }
]
"""


SYSTEM_POLICY = """
당신은 개인정보 마스킹 정책을 결정하는 전문가입니다.

판단 규칙

1. internal_policy를 가장 우선합니다.
2. internal_policy.metadata.action이 있으면 그대로 따릅니다.
3. internal_policy.content를 참고합니다.
4. official_evidence는 internal_policy가 부족할 때만 참고합니다.
5. 관련 없는 근거는 무시합니다.

action은 아래 중 하나만 사용합니다.

- keep
- partial
- remove

partial인 경우에는 반드시 masked_value를 생성합니다.

반드시 JSON 객체 하나만 출력합니다.
Markdown 코드블록(``` 또는 ```json)을 절대 사용하지 않습니다.
설명, 주석, 서론, 결론은 출력하지 않습니다.
JSON 이외의 어떠한 문자도 출력하지 않습니다.

{
  "item_id": "...",
  "action": "...",
  "masked_value": "...",
  "basis": {
      "doc": "...",
      "clause": "...",
      "summary": "..."
  }
}
"""


def build_detection_prompt(text: str) -> list[dict]:
    """
    이름/주소 탐지 프롬프트 생성
    """

    return [
        {
            "role": "system",
            "content": SYSTEM_DETECTION,
        },
        {
            "role": "user",
            "content": text,
        },
    ]


def build_policy_prompt(
    target: Target,
    detected_item: DetectedItem,
    rag_results: dict,
) -> list[dict]:
    """
    마스킹 정책 생성 프롬프트
    """

    user_prompt = f"""
대상:
{target}

개인정보:

- id: {detected_item.id}
- type: {detected_item.type}
- value: {detected_item.value}

RAG 결과:

{rag_results}

위 정보를 바탕으로
MaskingPolicy JSON 하나만 생성하세요.
"""

    return [
        {
            "role": "system",
            "content": SYSTEM_POLICY,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]