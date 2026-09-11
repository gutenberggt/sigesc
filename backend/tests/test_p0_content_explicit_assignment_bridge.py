from pathlib import Path


def test_explicit_assignment_keeps_classwide_read_inside_dvd_bridge():
    """Meus Diários deve usar o mesmo bridge DVD na leitura e na escrita."""
    root = Path(__file__).resolve().parents[2]
    resolver = (
        root / "frontend/src/services/contentPartialCutoverResolver.js"
    ).read_text(encoding="utf-8")
    dvd_bridge = (
        root / "frontend/src/services/contentDvdBridge.js"
    ).read_text(encoding="utf-8")

    explicit_guard = "if (hasExplicitAssignment()) return config;"
    classwide_gate = "config.__contentPartialCutoverClassWide = true;"
    list_gate = "if (method !== 'get' || !isLearningObjectsList(config.url)) return config;"

    assert explicit_guard in resolver
    assert classwide_gate in resolver
    assert list_gate in resolver

    # O contexto explícito precisa sair do resolver parcial antes de qualquer
    # decisão que marcaria o GET class-wide com __skipContentDvdBridge.
    assert resolver.index(explicit_guard) < resolver.index(list_gate)
    assert resolver.index(explicit_guard) < resolver.index(classwide_gate)

    # O bridge DVD é quem agrega os siblings e alimenta o cache necessário para
    # atualizar/excluir os cinco campos de experiência de um mesmo dia.
    assert "for (const sibling of config.__contentDvdList.siblings || [])" in dvd_bridge
    assert "cacheRecords(items);" in dvd_bridge
    assert "const current = recordCache.get(id);" in dvd_bridge
    assert "CONTENT_RELOAD_REQUIRED" in dvd_bridge


def test_generic_professor_flow_still_uses_f4_backend_adapter():
    """A correção do contexto explícito não pode regredir a PR #675."""
    root = Path(__file__).resolve().parents[2]
    resolver = (
        root / "frontend/src/services/contentPartialCutoverResolver.js"
    ).read_text(encoding="utf-8")

    assert "!hasExplicitAssignment()" in resolver
    assert "(method === 'put' || method === 'delete')" in resolver
    assert "isLearningObjectsRecord(config.url)" in resolver
    assert "config.__contentPartialCutoverFormWrite = true;" in resolver
