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


def test_new_pdf_service_compiles():
    compile(PDF_SERVICE.read_text(encoding="utf-8"), str(PDF_SERVICE), "exec")
    compile(ADAPTER.read_text(encoding="utf-8"), str(ADAPTER), "exec")
