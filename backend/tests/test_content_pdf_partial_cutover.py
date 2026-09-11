from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ADAPTER = BACKEND / "routers" / "content_partial_cutover.py"
PDF_SERVICE = BACKEND / "services" / "content_pdf_partial_cutover.py"


def test_professor_pdf_without_assignment_uses_same_cutover_projection_as_screen():
    adapter = ADAPTER.read_text(encoding="utf-8")
    service = PDF_SERVICE.read_text(encoding="utf-8")

    assert '"/learning-objects/pdf/bimestre/{class_id}"' in adapter
    assert "generate_professor_classwide_pdf" in adapter
    assert 'current_user.get("role") != "professor" or assignment_id' in adapter
    assert "list_learning_objects_cutover(" in service
    assert "legacy_items=[]" in service


def test_explicit_assignment_pdf_remains_under_previous_dvd_adapter():
    adapter = ADAPTER.read_text(encoding="utf-8")

    assert "if current_user.get(\"role\") != \"professor\" or assignment_id:" in adapter
    assert "return await previous_pdf(*args, **call_kwargs)" in adapter


def test_pdf_period_filter_accepts_records_after_04_september_inside_third_bimester():
    service = PDF_SERVICE.read_text(encoding="utf-8")

    # Regressão do caso real: o PDF não pode ficar preso ao último registro
    # legado de 04/09 quando a projeção canônica contém 10/09.
    assert "period_start <= str(item.get(\"date\") or \"\")[:10] <= period_end" in service
    assert "list_learning_objects_cutover(" in service
    assert "learning_objects.find(" not in service


def test_pdf_resolves_bimester_before_projection_and_reuses_monthly_reader():
    service = PDF_SERVICE.read_text(encoding="utf-8")

    # O incidente Failed to fetch surgiu após o PDF materializar a projeção do
    # ano inteiro (month=None) antes de conhecer o intervalo do bimestre.
    period_pos = service.index("period_start, period_end = _period_bounds(")
    projection_pos = service.index("batches = await asyncio.gather(")
    assert period_pos < projection_pos
    assert "months = _period_months(period_start, period_end)" in service
    assert "month=month" in service
    assert "month=None" not in service


def test_pdf_historical_aula_number_is_fail_safe_and_errors_are_normalized():
    service = PDF_SERVICE.read_text(encoding="utf-8")

    # Dados históricos heterogêneos não podem derrubar a ordenação do relatório.
    assert "def _safe_aula_numero(" in service
    assert "except (TypeError, ValueError):" in service
    assert "_safe_aula_numero(item.get(\"aula_numero\"))" in service

    # Exceções inesperadas devem virar resposta HTTP controlada, nunca conexão
    # abortada que o navegador apresenta apenas como `Failed to fetch`.
    assert "except HTTPException:" in service
    assert "except Exception as exc:" in service
    assert "status_code=500" in service
    assert "logger.exception(" in service


def test_pdf_queries_class_mantenedora_and_courses_in_active_tenant():
    service = PDF_SERVICE.read_text(encoding="utf-8")

    assert "tenant_id = get_mantenedora_scope(current_user, request)" in service
    assert '{"id": class_id, "mantenedora_id": tenant_id}' in service
    assert "get_mantenedora_cached(db, tenant_id)" in service
    assert '{"id": {"$in": course_ids}, "mantenedora_id": tenant_id}' in service


def test_new_pdf_service_compiles():
    compile(PDF_SERVICE.read_text(encoding="utf-8"), str(PDF_SERVICE), "exec")
    compile(ADAPTER.read_text(encoding="utf-8"), str(ADAPTER), "exec")
