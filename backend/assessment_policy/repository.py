"""Persistência tenant-scoped da Assessment Policy v1.

O repository não é instalado no startup nesta sprint. Todos os métodos exigem
`mantenedora_id` explícito nas leituras/mutações para preservar fail-closed.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from .models import AssessmentPolicy, PolicyStatus


COLLECTION_NAME = "assessment_policies"


class AssessmentPolicyRepository:
    """Adapter Mongo mínimo para o futuro Registry."""

    def __init__(self, db):
        self.collection = db[COLLECTION_NAME]

    async def get(self, policy_id: str, mantenedora_id: str) -> Optional[AssessmentPolicy]:
        doc = await self.collection.find_one(
            {"id": policy_id, "mantenedora_id": mantenedora_id},
            {"_id": 0},
        )
        return AssessmentPolicy.model_validate(doc) if doc else None

    async def insert(self, policy: AssessmentPolicy) -> AssessmentPolicy:
        await self.collection.insert_one(policy.model_dump(mode="json"))
        return policy

    async def replace_if_status(
        self,
        policy: AssessmentPolicy,
        expected_statuses: Iterable[PolicyStatus],
    ) -> bool:
        statuses = [status.value for status in expected_statuses]
        result = await self.collection.replace_one(
            {
                "id": policy.id,
                "mantenedora_id": policy.mantenedora_id,
                "status": {"$in": statuses},
            },
            policy.model_dump(mode="json"),
            upsert=False,
        )
        return result.matched_count == 1

    async def list_by_tenant(
        self,
        mantenedora_id: str,
        *,
        academic_year: Optional[int] = None,
        statuses: Optional[Iterable[PolicyStatus]] = None,
    ) -> List[AssessmentPolicy]:
        query = {"mantenedora_id": mantenedora_id}

        if academic_year is not None:
            query["academic_year"] = academic_year
        if statuses is not None:
            query["status"] = {"$in": [status.value for status in statuses]}

        cursor = self.collection.find(query, {"_id": 0}).sort(
            [("academic_year", -1), ("policy_key", 1), ("version", -1)]
        )
        docs = await cursor.to_list(length=None)
        return [AssessmentPolicy.model_validate(doc) for doc in docs]

    async def exists_policy_version(
        self,
        mantenedora_id: str,
        policy_key: str,
        version: int,
    ) -> bool:
        count = await self.collection.count_documents(
            {
                "mantenedora_id": mantenedora_id,
                "policy_key": policy_key,
                "version": version,
            },
            limit=1,
        )
        return count > 0
