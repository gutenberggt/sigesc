from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = REPO_ROOT / "frontend" / "src" / "pages"
COMPONENTS_DIR = REPO_ROOT / "frontend" / "src" / "components"
CONTEXTS_DIR = REPO_ROOT / "frontend" / "src" / "contexts"
PAGE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
SET_INTERVAL_RE = re.compile(r"\b(?:window\.)?setInterval\s*\(")

# Polling técnico de jobs assíncronos não é atualização automática de dados da
# página: sem ele, a geração do documento não conclui na UI. Qualquer nova
# exceção precisa ser deliberada e adicionada explicitamente aqui.
TECHNICAL_POLLING_ALLOWLIST = {
    "StudentHistory.js": "/render-jobs/",
    "BulletinViewer.jsx": "/render-jobs/",
}


def _page_sources():
    for path in sorted(PAGES_DIR.rglob("*")):
        if path.is_file() and path.suffix in PAGE_EXTENSIONS:
            yield path.relative_to(PAGES_DIR).as_posix(), path.read_text(encoding="utf-8")


def test_pages_do_not_use_recurring_auto_refresh_timers():
    offenders = []
    for relative_path, source in _page_sources():
        if SET_INTERVAL_RE.search(source) and relative_path not in TECHNICAL_POLLING_ALLOWLIST:
            offenders.append(relative_path)

    assert offenders == [], (
        "Páginas do SIGESC não devem atualizar dados periodicamente por setInterval. "
        "Mantenha carga inicial e, quando já existir, o botão manual Atualizar. "
        f"Ofensores: {offenders}"
    )


def test_technical_polling_allowlist_is_limited_to_render_jobs():
    for relative_path, required_marker in TECHNICAL_POLLING_ALLOWLIST.items():
        source = (PAGES_DIR / relative_path).read_text(encoding="utf-8")
        assert SET_INTERVAL_RE.search(source), f"Exceção obsoleta: {relative_path} não usa mais setInterval"
        assert required_marker in source, (
            f"{relative_path} só pode permanecer na allowlist enquanto o intervalo for polling "
            "técnico de renderização de documento."
        )


def test_online_users_is_manual_refresh_only():
    source = (PAGES_DIR / "OnlineUsers.js").read_text(encoding="utf-8")

    assert not SET_INTERVAL_RE.search(source)
    assert 'data-testid="refresh-online-users"' in source
    assert "Atualizar" in source
    assert "atualiza automaticamente" not in source.lower()


def test_learning_objects_has_no_recurring_refresh_timer():
    source = (PAGES_DIR / "LearningObjects.js").read_text(encoding="utf-8")
    assert not SET_INTERVAL_RE.search(source)


def test_background_access_revalidation_does_not_unmount_the_current_page():
    protected_route = (COMPONENTS_DIR / "ProtectedRoute.js").read_text(encoding="utf-8")
    mantenedora_context = (CONTEXTS_DIR / "MantenedoraContext.js").read_text(encoding="utf-8")

    # A revalidação periódica de segurança continua existindo.
    assert "window.setInterval(() => loadAccessStatus(), 60000)" in mantenedora_context

    # Mas o loader de rota só pode entrar quando ainda não há accessStatus conhecido.
    # Revalidações em background precisam manter a página montada para preservar
    # formulários e rascunhos locais (Objetos de Conhecimento, notas, frequência etc.).
    assert re.search(
        r"const\s+isInitialAccessCheck\s*=\s*Boolean\(user\s*&&\s*accessLoading\s*&&\s*!accessStatus\)",
        protected_route,
    )
    assert "if (loading || isInitialAccessCheck)" in protected_route
    assert "if (loading || (user && accessLoading))" not in protected_route
