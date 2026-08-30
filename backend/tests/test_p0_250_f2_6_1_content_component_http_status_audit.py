from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p0_250_f2_6_1_content_component_http_status_audit.py"
spec = importlib.util.spec_from_file_location("p0_250_f2_6_1", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def month(status=200, mongo=2, component_http=2, classwide_http=2, management_http=2):
    return {
        "mongo_target_tenant": mongo,
        "professor_classwide_status": 200,
        "professor_classwide_http": classwide_http,
        "professor_component_status": status,
        "professor_component_http": component_http if status == 200 else 0,
        "superadmin_scoped_status": 200,
        "superadmin_scoped_http": management_http,
    }


def row(name, focus=None):
    return {
        "component_name": name,
        "focus": focus,
        "legacy_assignment_count": 1,
        "present_in_professor_turmas_http": True,
        "dvd_raw_component_rows": 1,
        "dvd_enabled_current_component_rows": 0,
        "months": {str(m): month() for m in module.TARGET_MONTHS},
    }


def rows9():
    names = [
        ("Arte", None), ("Ciências", None), ("Educação Física", None),
        ("Ensino Religioso", None), ("Geografia", None), ("História", None),
        ("Língua Portuguesa", "PORTUGUES"), ("Matemática", "MATEMATICA"),
        ("Educação Ambiental e Clima", None),
    ]
    return [row(name, focus) for name, focus in names]


def test_parity():
    result = module.analyze_http_status_parity(
        component_rows=rows9(), classwide_statuses={"4": 200, "5": 200, "6": 200}
    )
    assert result["classification"] == "CONTENT_COMPONENT_HTTP_DB_PARITY"


def test_component_409_has_priority_and_names_component():
    rows = rows9()
    portuguese = next(r for r in rows if r["focus"] == "PORTUGUES")
    portuguese["months"]["6"] = month(status=409)
    result = module.analyze_http_status_parity(
        component_rows=rows, classwide_statuses={"4": 409, "5": 409, "6": 409}
    )
    assert result["classification"] == "CONTENT_COMPONENT_PROFESSOR_COMPONENT_BLOCKED"
    assert result["blocked_components"] == [
        {"component_name": "Língua Portuguesa", "focus": "PORTUGUES", "months": [6]}
    ]


def test_classwide_409_is_diagnostic_not_fatal():
    result = module.analyze_http_status_parity(
        component_rows=rows9(), classwide_statuses={"4": 409, "5": 409, "6": 409}
    )
    assert result["classification"] == "CONTENT_COMPONENT_PROFESSOR_CLASSWIDE_BLOCKED"


def test_professor_count_gap_after_200():
    rows = rows9()
    math = next(r for r in rows if r["focus"] == "MATEMATICA")
    math["months"]["5"] = month(mongo=3, component_http=1, classwide_http=1, management_http=3)
    result = module.analyze_http_status_parity(
        component_rows=rows, classwide_statuses={"4": 200, "5": 200, "6": 200}
    )
    assert result["classification"] == "CONTENT_COMPONENT_HTTP_PROFESSOR_GAP"


def test_focus_normalization():
    assert module._focus_component("Língua Portuguesa") == "PORTUGUES"
    assert module._focus_component("Português") == "PORTUGUES"
    assert module._focus_component("Matemática") == "MATEMATICA"
