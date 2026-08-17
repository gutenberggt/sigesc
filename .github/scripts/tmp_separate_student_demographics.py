#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend/routers/students.py"
FRONTEND = ROOT / "frontend/src/pages/StudentsComplete.js"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if new in text:
            print(f"{label}: já aplicado")
            return text
        raise SystemExit(f"{label}: âncora não encontrada")
    if count != 1:
        raise SystemExit(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)


backend = BACKEND.read_text(encoding="utf-8")
backend = replace_once(
    backend,
    '''        # Contagem por série.\n''',
    '''        # Contagem por comunidade tradicional (dimensão separada de cor/raça).\n        traditional_community_counts = {}\n        community_pipeline = [\n            {"$match": active_filter},\n            {"$group": {\n                "_id": {"$ifNull": ["$comunidade_tradicional", "nao_informada"]},\n                "count": {"$sum": 1}\n            }}\n        ]\n        community_cursor = current_db.students.aggregate(community_pipeline)\n        async for doc in community_cursor:\n            community_key = doc["_id"] if doc["_id"] else "nao_informada"\n            if community_key == "":\n                community_key = "nao_informada"\n            traditional_community_counts[community_key] = doc["count"]\n\n        # Contagem por série.\n''',
    "backend: contagem comunidade",
)
backend = replace_once(
    backend,
    '''            "race_counts": race_counts,\n            "series_counts": series_counts,\n''',
    '''            "race_counts": race_counts,\n            "traditional_community_counts": traditional_community_counts,\n            "series_counts": series_counts,\n''',
    "backend: resposta comunidade",
)
BACKEND.write_text(backend, encoding="utf-8")

frontend = FRONTEND.read_text(encoding="utf-8")
frontend = replace_once(
    frontend,
    '''  const [raceCounts, setRaceCounts] = useState({});\n  const [seriesCounts, setSeriesCounts] = useState({});\n''',
    '''  const [raceCounts, setRaceCounts] = useState({});\n  const [traditionalCommunityCounts, setTraditionalCommunityCounts] = useState({});\n  const [seriesCounts, setSeriesCounts] = useState({});\n''',
    "frontend: estado comunidade",
)
frontend = replace_once(
    frontend,
    '''        setRaceCounts(result.race_counts || {});\n        setSeriesCounts(result.series_counts || {});\n''',
    '''        setRaceCounts(result.race_counts || {});\n        setTraditionalCommunityCounts(result.traditional_community_counts || {});\n        setSeriesCounts(result.series_counts || {});\n''',
    "frontend: carregar comunidade",
)
frontend = replace_once(
    frontend,
    '''                        { key: 'amarela', label: 'Amarela' },\n                        { key: 'indigena', label: 'Indígena' },\n                        { key: 'cigano', label: 'Cigano' },\n                        { key: 'quilombola', label: 'Quilombola' },\n                        { key: 'ribeirinho', label: 'Ribeirinho' },\n                        { key: 'extrativista', label: 'Extrativista' },\n''',
    '''                        { key: 'amarela', label: 'Amarela' },\n                        { key: 'indigena', label: 'Indígena' },\n''',
    "frontend: remover comunidades de raça",
)
frontend = replace_once(
    frontend,
    '''                  </div>\n\n                  {/* ENSINO FUNDAMENTAL */}\n                  <div data-testid="series-anos-counts">\n''',
    '''                  </div>\n\n                  {/* COMUNIDADES TRADICIONAIS */}\n                  <div data-testid="traditional-community-counts">\n                    <p className="text-[11px] font-semibold tracking-wider text-gray-400 uppercase mb-2">\n                      Comunidades Tradicionais\n                    </p>\n                    <div className="flex flex-wrap gap-2">\n                      {[\n                        { key: 'quilombola', label: 'Quilombola' },\n                        { key: 'cigano', label: 'Cigano' },\n                        { key: 'ribeirinho', label: 'Ribeirinho' },\n                        { key: 'extrativista', label: 'Extrativista' },\n                      ].map(({ key, label }) => (\n                        <span\n                          key={key}\n                          className="inline-flex items-center px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium"\n                        >\n                          {label}: {traditionalCommunityCounts[key] || 0}\n                        </span>\n                      ))}\n                    </div>\n                  </div>\n\n                  {/* ENSINO FUNDAMENTAL */}\n                  <div data-testid="series-anos-counts">\n''',
    "frontend: bloco comunidades",
)
FRONTEND.write_text(frontend, encoding="utf-8")

print("Separação Cor/Raça × Comunidades Tradicionais aplicada com sucesso.")
