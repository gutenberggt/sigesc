from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperado 1 match, encontrado {count}")
    return text.replace(old, new, 1)


path = Path("backend/routers/content_entries.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "    observations: Optional[str] = Field(default=None, max_length=5000)\n\n\nasync def _resolve_class_info",
    "    observations: Optional[str] = Field(default=None, max_length=5000)\n"
    "    number_of_classes: Optional[int] = Field(default=None, ge=1)\n\n\n"
    "async def _resolve_class_info",
    "correct model",
)

text = replace_once(
    text,
    "        if payload.content is None and payload.methodology is None and payload.observations is None:\n",
    "        if (\n"
    "            payload.content is None\n"
    "            and payload.methodology is None\n"
    "            and payload.observations is None\n"
    "            and payload.number_of_classes is None\n"
    "        ):\n",
    "empty correction",
)

text = replace_once(
    text,
    '                    "message": "Informe pelo menos um campo a corrigir (content, methodology ou observations).",\n',
    '                    "message": (\n'
    '                        "Informe pelo menos um campo a corrigir "\n'
    '                        "(content, methodology, observations ou number_of_classes)."\n'
    '                    ),\n',
    "empty correction message",
)

text = replace_once(
    text,
    "        if payload.observations is not None:\n            set_fields[\"observations\"] = payload.observations\n\n        await db.content_entries.update_one",
    "        if payload.observations is not None:\n"
    "            set_fields[\"observations\"] = payload.observations\n"
    "        if payload.number_of_classes is not None:\n"
    "            set_fields[\"number_of_classes\"] = payload.number_of_classes\n\n"
    "        await db.content_entries.update_one",
    "correct set fields",
)

path.write_text(text, encoding="utf-8")
print("PHASE38F_CORRECT_PATCH_OK")
