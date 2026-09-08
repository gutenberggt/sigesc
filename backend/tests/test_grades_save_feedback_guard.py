from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "frontend" / "src" / "components" / "PainelSincronizacao.jsx"


def source() -> str:
    return PANEL.read_text(encoding="utf-8")


def test_online_grade_batch_failure_is_observed():
    text = source()
    assert "url.includes('/grades/batch')" in text
    assert "axios.interceptors.response.use" in text
    assert "setDirectGradeSaveError" in text
    assert "extractErrorMessage" in text


def test_direct_grade_failure_has_priority_over_green_summary():
    text = source()
    assert "if (directGradeSaveError) estado = 'falha_direta_notas';" in text
    assert "A última tentativa de salvar notas falhou" in text
    assert "directError={c === 'grades' && Boolean(directGradeSaveError)}" in text
    assert "Falha no último envio" in text


def test_successful_direct_grade_save_clears_error_and_updates_last_send_time():
    text = source()
    assert "setDirectGradeSaveError(null);" in text
    assert "setDirectGradeSaveTime(new Date());" in text
    assert "newestDate(lastSyncTime, directGradeSaveTime)" in text


def test_existing_offline_states_remain_available():
    text = source()
    for expected in (
        "Você está sem internet",
        "Tudo salvo e enviado",
        "aguardando envio",
        "não enviado",
    ):
        assert expected in text
