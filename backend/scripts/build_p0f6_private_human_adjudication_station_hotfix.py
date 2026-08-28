"""P0-F6.1 — hotfix de renderização JavaScript da estação P0-F6.

Reutiliza integralmente o P0-F6 original e corrige somente a emissão do literal
``\n`` usado no JSON exportado pelo navegador. O P0-F6 original produz uma quebra
de linha física dentro de uma string JavaScript, causando SyntaxError no browser.

Este módulo não acessa banco de dados e não altera a semântica de adjudicação ou
selagem. É uma camada corretiva compatível e fail-closed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

BASE_PATH = Path(__file__).resolve().with_name(
    "build_p0f6_private_human_adjudication_station.py"
)

spec = importlib.util.spec_from_file_location("p0f6_base", BASE_PATH)
if not spec or not spec.loader:
    raise RuntimeError("P0F6_BASE_IMPORT_FAILED")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

P0F5_PHASE = base.P0F5_PHASE
STATION_PHASE = base.STATION_PHASE
RAW_DECISION_PHASE = base.RAW_DECISION_PHASE
SEALED_DECISION_PHASE = base.SEALED_DECISION_PHASE
MANIFEST_VERSION = base.MANIFEST_VERSION
ALLOWED_DECISIONS = base.ALLOWED_DECISIONS
canonical_sha256 = base.canonical_sha256
validate_p0f5_packet = base.validate_p0f5_packet
validate_raw_decisions = base.validate_raw_decisions
seal_decisions = base.seal_decisions

_BROKEN_EXPORT_LITERAL = "JSON.stringify(payload,null,2)+'\n']"
_FIXED_EXPORT_LITERAL = "JSON.stringify(payload,null,2)+'\\n']"


def repair_generated_html(html_text: str) -> str:
    """Corrige unicamente o newline físico inválido na string JavaScript."""
    broken_count = html_text.count(_BROKEN_EXPORT_LITERAL)
    fixed_count = html_text.count(_FIXED_EXPORT_LITERAL)

    if broken_count == 1 and fixed_count == 0:
        repaired = html_text.replace(
            _BROKEN_EXPORT_LITERAL,
            _FIXED_EXPORT_LITERAL,
            1,
        )
    elif broken_count == 0 and fixed_count == 1:
        # Compatibilidade futura caso a base seja corrigida diretamente.
        repaired = html_text
    else:
        raise RuntimeError(
            "P0F6_JS_NEWLINE_PATTERN_UNEXPECTED "
            f"broken={broken_count} fixed={fixed_count}"
        )

    if _BROKEN_EXPORT_LITERAL in repaired:
        raise RuntimeError("P0F6_JS_NEWLINE_REPAIR_INCOMPLETE")
    if repaired.count(_FIXED_EXPORT_LITERAL) != 1:
        raise RuntimeError("P0F6_JS_NEWLINE_FIXED_LITERAL_COUNT_MISMATCH")
    return repaired


def build_station(packet_path: Path, output_path: Path) -> dict[str, Any]:
    packet = base.load_json(packet_path)
    validation = base.validate_p0f5_packet(packet)
    html_text = base.build_station_html(packet, validation)
    html_text = repair_generated_html(html_text)
    base.private_write_text(output_path, html_text)

    return {
        "phase": STATION_PHASE,
        "hotfix_phase": "P0F6.1-JS-NEWLINE-ESCAPE-HOTFIX-2026",
        "status": "PASS",
        "source_p0f5_manifest_sha256": validation["packet_sha256"],
        "review_units": validation["review_unit_count"],
        "output_file_mode": oct(output_path.stat().st_mode & 0o777)[2:].zfill(4),
        "network_dependencies": 0,
        "javascript_newline_escape_repaired": True,
        "automatic_recommendation": False,
        "database_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-F6.1 hotfix da estação offline de adjudicação humana"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Gerar HTML P0-F6 com hotfix de JS")
    build.add_argument("--packet", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)

    seal = sub.add_parser("seal", help="Delegar selagem ao contrato P0-F6 original")
    seal.add_argument("--packet", required=True, type=Path)
    seal.add_argument("--decisions", required=True, type=Path)
    seal.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "build":
        result = build_station(args.packet, args.output)
    else:
        result = base.seal_decisions(args.packet, args.decisions, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
