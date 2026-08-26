from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.coolify.yml"


def _backend_block(src: str) -> str:
    assert "  backend:\n" in src
    assert "\n  frontend:\n" in src
    return src.split("  backend:\n", 1)[1].split("\n  frontend:\n", 1)[0]


def _volumes_block(src: str) -> str:
    assert "\nvolumes:\n" in src
    return src.split("\nvolumes:\n", 1)[1].split("\n# ====", 1)[0]


def test_backend_monta_volume_persistente_para_backups_dvd():
    src = COMPOSE.read_text(encoding="utf-8")
    backend = _backend_block(src)

    assert "    volumes:\n" in backend
    assert "      - sigesc-dvd-backups:/data/sigesc-dvd-backups\n" in backend
    assert "/tmp/dvd" not in backend


def test_backend_monta_volume_persistente_para_backups_de_horarios():
    src = COMPOSE.read_text(encoding="utf-8")
    backend = _backend_block(src)

    assert "      - sigesc-schedule-backups:/data/sigesc-schedule-backups\n" in backend
    assert "sigesc-schedule-backups:/data\n" not in backend


def test_volumes_persistentes_estao_declarados_no_escopo_global_do_compose():
    src = COMPOSE.read_text(encoding="utf-8")
    volumes = _volumes_block(src)

    assert "  sigesc-mongo-data:\n" in volumes
    assert "  sigesc-dvd-backups:\n" in volumes
    assert "  sigesc-schedule-backups:\n" in volumes


def test_frontend_nao_recebe_volumes_de_backup():
    src = COMPOSE.read_text(encoding="utf-8")
    frontend = src.split("\n  frontend:\n", 1)[1].split("\nvolumes:\n", 1)[0]

    assert "sigesc-dvd-backups" not in frontend
    assert "/data/sigesc-dvd-backups" not in frontend
    assert "sigesc-schedule-backups" not in frontend
    assert "/data/sigesc-schedule-backups" not in frontend
