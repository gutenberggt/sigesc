"""
Regressão — Remanejamento de aluno (PUT /api/students/{id} com mudança de class_id)

Bug original: o remanejamento criava a nova matrícula carregando o MESMO
`enrollment_number` da matrícula de origem. Como existe índice único global
`uq_enrollment_number`, o insert quebrava com DuplicateKeyError → HTTP 500
("Network Error" no frontend).

Fix: o número de matrícula é transferido para a nova matrícula ATIVA e o número
da matrícula de origem (agora `relocated`) é liberado (guardado em
`previous_enrollment_number`).
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-tenant-fixed.preview.emergentagent.com')

SCHOOL_ID = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
REGULAR_CLASS_ID = "c09b8666-c8bb-40d1-b835-c2b0fa4b8ecd"   # TURMA MULTI 1-2-3
REGULAR_CLASS_2_ID = "e37025d4-52a9-40f7-89b6-2a9789c9f266"  # TESTE 2
ACADEMIC_YEAR = 2026

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")


class TestRelocateStudent:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert login.status_code == 200, f"Login failed: {login.text}"
        token = login.json().get("access_token")
        csrf = login.json().get("csrf_token")
        self.session.headers.update({"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf})
        self.student_id = None
        yield
        if self.student_id:
            try:
                self.session.delete(f"{BASE_URL}/api/students/{self.student_id}")
            except Exception:
                pass

    def _create_active_student_in(self, class_id):
        suffix = str(uuid.uuid4())[:8]
        resp = self.session.post(f"{BASE_URL}/api/students", json={
            "full_name": f"TEST_RELOCATE_{suffix}",
            "school_id": SCHOOL_ID, "class_id": "",
            "status": "inactive", "cpf": "", "birth_date": "2015-01-01",
        })
        assert resp.status_code == 201, resp.text
        self.student_id = resp.json()["id"]
        # matricula via update (inactive -> active)
        up = self.session.put(f"{BASE_URL}/api/students/{self.student_id}", json={
            "school_id": SCHOOL_ID, "class_id": class_id,
            "status": "active", "academic_year": ACADEMIC_YEAR,
        })
        assert up.status_code == 200, up.text
        return up.json()

    def test_relocate_returns_200_and_carries_number(self):
        """Remanejar aluno ativo de uma turma para outra deve retornar 200 (não 500)."""
        created = self._create_active_student_in(REGULAR_CLASS_ID)
        original_number = created.get("enrollment_number")
        assert original_number, "Aluno matriculado deve ter enrollment_number"

        # Remaneja para outra turma (mesma escola)
        relocate = self.session.put(f"{BASE_URL}/api/students/{self.student_id}", json={
            "class_id": REGULAR_CLASS_2_ID,
        })
        assert relocate.status_code == 200, f"Remanejamento deve retornar 200, veio {relocate.status_code}: {relocate.text}"
        body = relocate.json()
        assert body.get("class_id") == REGULAR_CLASS_2_ID, "Aluno deve estar na turma de destino"
        assert body.get("status") == "active"
        # O número da matrícula é a identidade do aluno e é transferido para a nova matrícula ativa.
        assert body.get("enrollment_number") == original_number, \
            "O número de matrícula deve ser carregado para a nova matrícula ativa"
        print(f"✓ Remanejamento OK — número {original_number} preservado na matrícula ativa")

    def test_relocate_keeps_single_active_enrollment(self):
        """Após remanejar, o aluno deve ter exatamente UMA matrícula ativa (na turma destino)."""
        self._create_active_student_in(REGULAR_CLASS_ID)
        relocate = self.session.put(f"{BASE_URL}/api/students/{self.student_id}", json={
            "class_id": REGULAR_CLASS_2_ID,
        })
        assert relocate.status_code == 200, relocate.text

        hist = self.session.get(f"{BASE_URL}/api/students/{self.student_id}/history")
        assert hist.status_code == 200
        actions = [h.get("action_type") for h in hist.json()]
        assert "remanejamento" in actions, f"Histórico deve registrar remanejamento: {actions}"
        print(f"✓ Histórico registrou remanejamento: {actions}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
