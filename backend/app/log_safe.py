"""로그에 개인정보가 남지 않게 하는 헬퍼.

마스킹 서비스가 정작 서버 로그로 이름·주소를 흘리면 서비스 자체가 무의미해진다.
탐지값과 OCR 원문은 원칙적으로 로그에 남기지 않고, 실패 로그에는 item_id와 type만 남긴다.
디버깅상 값이 꼭 필요한 경우(로컬 데모 등)에만 mask_for_log를 거친다.
"""

_MAX_STARS = 8


def mask_for_log(value: str | None) -> str:
    """첫 글자만 남기고 가린다. (김민수 -> 김**)

    주소처럼 긴 값이 별표 수십 개로 늘어나 로그를 덮지 않도록 길이를 제한한다.
    """
    if not value:
        return ""
    return value[0] + "*" * min(len(value) - 1, _MAX_STARS)


def exc_label(e: BaseException) -> str:
    """예외를 로그에 남길 때 쓰는 라벨. 메시지 본문은 버리고 종류만 남긴다.

    LLM/OCR 응답 파싱 실패 예외(json.JSONDecodeError 등)는 메시지에 응답 본문
    조각을 그대로 담는다. 그 본문이 바로 탐지된 이름·주소라서, str(e)를 찍으면
    "탐지 실패" 로그를 통해 개인정보가 그대로 샌다.
    HTTP 오류는 상태 코드만 있으면 원인 파악에 충분하므로 함께 남긴다.
    """
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status is not None:
        return f"{type(e).__name__}(status={status})"
    return type(e).__name__
