from typing import List

from backend.app.schemas import (
    DetectedItem,
    MaskingPolicy,
    Target,
)

from .llm_client import ClovaClient
from rag.rag_pipeline import run_rag


client = ClovaClient()


def generate_policy(
    item: DetectedItem,
    target: Target,
) -> MaskingPolicy:
    """
    개인정보 1건에 대한 마스킹 정책 생성
    """

    rag_result = run_rag(
        pii_type=item.type,
        target=target,
    )

    return client.decide_policy(
        target=target,
        detected_item=item,
        rag_results=rag_result["rag_results"],
    )


def generate_policies(
    detected_items: List[DetectedItem],
    target: Target,
) -> List[MaskingPolicy]:
    """
    개인정보 목록에 대한 마스킹 정책 생성
    """

    return [
        generate_policy(item, target)
        for item in detected_items
    ]