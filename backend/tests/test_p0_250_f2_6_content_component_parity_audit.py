from pathlib import Path
import importlib.util
import sys
import types


# Unit tests exercise the pure classifier only; production supplies pymongo inside
# the backend container. Keep this guard test independent from external packages.
fake_pymongo = types.ModuleType("pymongo")
fake_pymongo.MongoClient = object
sys.modules.setdefault("pymongo", fake_pymongo)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "p0_250_f2_6_content_component_parity_audit.py"
spec = importlib.util.spec_from_file_location("p0_250_f2_6", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def month_counts(**overrides):
    base = {
        "mongo_all_tenants": 2,
        "mongo_target_tenant": 2,
        "mongo_missing_or_null_tenant": 0,
        "mongo_other_tenant": 0,
        "professor_classwide_http": 2,
        "professor_component_http": 2,
        "superadmin_unscoped_http": 2,
        "superadmin_scoped_http": 2,
    }
    base.update(overrides)
    return base


def row(name, focus=None, month_override=None):
    months = {str(month): month_counts() for month in module.TARGET_MONTHS}
    if month_override:
        month, values = month_override
        months[str(month)] = month_counts(**values)
    return {
        "component_name": name,
        "focus": focus,
        "legacy_assignment_count": 1,
        "present_in_professor_turmas_http": True,
        "dvd_raw_component_rows": 1,
        "dvd_enabled_current_component_rows": 0,
        "months": months,
    }


def nine_rows():
    names = [
        ("Arte", None),
        ("Ciências", None),
        ("Educação Física", None),
        ("Ensino Religioso", None),
        ("Geografia", None),
        ("História", None),
        ("Língua Portuguesa", "PORTUGUES"),
        ("Matemática", "MATEMATICA"),
        ("Educação Ambiental e Clima", None),
    ]
    return [row(name, focus) for name, focus in names]


def test_full_http_db_parity():
    result = module.analyze_component_parity(component_rows=nine_rows())
    assert result["classification"] == "CONTENT_COMPONENT_HTTP_DB_PARITY"
    assert result["component_count"] == 9
    assert set(result["focus_components"]) == {"PORTUGUES", "MATEMATICA"}


def test_professor_http_gap_has_priority():
    rows = nine_rows()
    target = next(item for item in rows if item["focus"] == "PORTUGUES")
    target["months"]["6"]["mongo_target_tenant"] = 3
    target["months"]["6"]["mongo_all_tenants"] = 3
    target["months"]["6"]["professor_classwide_http"] = 0
    target["months"]["6"]["professor_component_http"] = 0
    result = module.analyze_component_parity(component_rows=rows)
    assert result["classification"] == "CONTENT_COMPONENT_HTTP_PROFESSOR_GAP"


def test_classwide_projection_gap_is_distinct():
    rows = nine_rows()
    target = next(item for item in rows if item["focus"] == "MATEMATICA")
    target["months"]["5"]["professor_classwide_http"] = 1
    target["months"]["5"]["professor_component_http"] = 2
    target["months"]["5"]["mongo_target_tenant"] = 1
    target["months"]["5"]["mongo_all_tenants"] = 1
    result = module.analyze_component_parity(component_rows=rows)
    assert result["classification"] == "CONTENT_COMPONENT_CLASSWIDE_PROJECTION_GAP"


def test_tenant_scope_gap_identifies_superadmin_difference():
    rows = nine_rows()
    target = next(item for item in rows if item["focus"] == "PORTUGUES")
    target["months"]["4"] = month_counts(
        mongo_all_tenants=4,
        mongo_target_tenant=2,
        mongo_missing_or_null_tenant=2,
        professor_classwide_http=2,
        professor_component_http=2,
        superadmin_unscoped_http=4,
        superadmin_scoped_http=2,
    )
    result = module.analyze_component_parity(component_rows=rows)
    assert result["classification"] == "CONTENT_COMPONENT_TENANT_SCOPE_GAP"
    assert result["focus_components"]["PORTUGUES"]["months"]["4"]["mongo_missing_or_null_tenant"] == 2


def test_entitlement_drift_if_not_nine_components():
    result = module.analyze_component_parity(component_rows=nine_rows()[:-1])
    assert result["classification"] == "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"


def test_component_focus_normalization():
    assert module._focus_component("Língua Portuguesa") == "PORTUGUES"
    assert module._focus_component("Português") == "PORTUGUES"
    assert module._focus_component("MATEMÁTICA") == "MATEMATICA"
    assert module._focus_component("Ciências") is None
