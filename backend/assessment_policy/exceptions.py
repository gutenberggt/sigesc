"""Erros de domínio da Assessment Policy.

Sem dependência de FastAPI: adapters HTTP futuros traduzirão esses erros.
"""

from __future__ import annotations


class AssessmentPolicyError(Exception):
    """Erro determinístico do domínio de políticas avaliativas."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


POLICY_NOT_FOUND = "ASSESSMENT_POLICY_NOT_FOUND"
POLICY_IMMUTABLE = "ASSESSMENT_POLICY_IMMUTABLE"
POLICY_INVALID_STATE = "ASSESSMENT_POLICY_INVALID_STATE"
POLICY_TENANT_MISMATCH = "ASSESSMENT_POLICY_TENANT_MISMATCH"
POLICY_VALIDATION_FAILED = "ASSESSMENT_POLICY_VALIDATION_FAILED"
POLICY_CONFLICT_CHECK_REQUIRED = "ASSESSMENT_POLICY_CONFLICT_CHECK_REQUIRED"
POLICY_CONFLICT = "ASSESSMENT_POLICY_CONFLICT"
POLICY_CONCURRENT_MODIFICATION = "ASSESSMENT_POLICY_CONCURRENT_MODIFICATION"
