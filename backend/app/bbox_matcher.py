"""LLM이 값만 찾아온 이름/주소(bbox 없음)에, 원본 OCR 결과에서 실제 좌표를 찾아준다.

핵심 아이디어: LLM이 찾은 값 문자열을, OCR 필드들을 순서대로 이어붙이며 검색한다.
연속된 필드를 하나씩 이어붙여가다 값이 나타나면, 그 값이 실제로 걸쳐있는
필드들만 골라서 bbox를 합친다 (매칭 시작 위치를 문자 단위로 추적하기 때문에,
검색을 시작한 필드가 값과 무관한 라벨이어도 그 라벨까지 bbox에 섞이지 않는다).

used로 이미 매칭에 쓰인 필드를 추적해서, 같은 값이 문서에 여러 번 나와도
매번 다른 위치를 정확히 찾아낸다.
"""

from app.schemas import OcrPage


def _norm(s: str) -> str:
    """공백 유무와 상관없이 비교하기 위해 모든 공백을 제거한다."""
    return "".join(s.split())


def find_bbox(value: str, page: OcrPage, used: set) -> tuple[list[int] | None, set]:
    """value가 등장하는 필드(들)를 찾아 병합된 bbox를 반환한다.

    Returns:
        (bbox, updated_used) — 못 찾으면 (None, used 그대로)
    """
    target = _norm(value)
    fields = page.fields

    for i in range(len(fields)):
        if i in used:
            continue

        buf = ""
        field_spans = []  # (start, end, field_idx) - buf 안에서 각 필드가 차지하는 구간

        for j in range(i, min(i + 8, len(fields))):  # 최대 8개 필드까지 이어붙임
            if j in used:
                break

            start = len(buf)
            buf += _norm(fields[j].text)
            field_spans.append((start, len(buf), j))

            idx = buf.find(target)
            if idx != -1:
                m_end = idx + len(target)
                # 매칭된 구간(idx~m_end)에 실제로 걸치는 필드만 골라서 bbox 계산
                # (검색 시작 필드가 관계없는 라벨이어도 섞이지 않도록)
                covering = [k for (s, e, k) in field_spans if s < m_end and e > idx]
                boxes = [fields[k].bbox for k in covering]
                merged = [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
                return merged, used | set(covering)

            if len(buf) > len(target) * 2:  # 너무 길어지면 이 시작점은 포기
                break

    return None, used