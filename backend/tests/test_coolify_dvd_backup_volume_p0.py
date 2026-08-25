from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.coolify.yml"


def test_backend_monta_volume_persistente_para_backups_dvd():
    src = COMPOSE.read_text(encoding="utf-8")

    assert "  backend:\n" in src
    assert "\n  frontend:\n" in src

    backend = src.split("  backend:\n", 1)[1].split("\n  frontend:\n", 1)[0]

    assert "    volumes:\n" in backend
    assert "      - sigesc-dvd-backups:/data/sigesc-dvd-backups\n" in backend
    assert "/tmp/dvd" not in backend


def test_volume_dvd_esta_declarado_no_escopo_global_do_compose():
    src = COMPOSE.read_text(encoding="utf-8")

    assert "\nvolumes:\n" in src
    volumes = src.split("\nvolumes:\n", 1)[1].split("\n# ====", 1)[0]

    assert "  sigesc-mongo-data:\n" in volumes
    assert "  sigesc-dvd-backups:\n" in volumes


def test_frontend_nao_recebe_volume_de_backup_dvd():
    src = COMPOSE.read_text(encoding="utf-8")
    frontend = src.split("\n  frontend:\n", 1)[1].split("\nvolumes:\n", 1)[0]

    assert "sigesc-dvd-backups" not in frontend
    assert "/data/sigesc-dvd-backups" not in frontend
