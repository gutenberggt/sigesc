from pathlib import Path

p = Path('backend/services/enrollment_rectification.py')
text = p.read_text(encoding='utf-8')

start = text.index('async def _document_manifest(')
end = text.index('\n\nasync def build_rectification_dry_run(', start)
replacement = '''async def _document_manifest(\n    db,\n    *,\n    student_id: str,\n    source_class_id: str,\n    academic_year: int,\n    tenant_id: str,\n) -> dict[str, Any]:\n    # F2.1C: SSoT documental única. O dry-run permanece estritamente read-only.\n    from services.enrollment_rectification_documents import (\n        build_rectification_document_inventory,\n    )\n\n    return await build_rectification_document_inventory(\n        db,\n        student_id=student_id,\n        source_class_id=source_class_id,\n        academic_year=academic_year,\n        tenant_id=tenant_id,\n    )\n'''
text = text[:start] + replacement + text[end:]

block_start = text.index('    documents = await _document_manifest(')
block_end = text.index('    preserved_counts = {', block_start)
old_block = text[block_start:block_end]
call_end = old_block.index('    )\n', old_block.index('    documents =')) + len('    )\n')
doc_call = old_block[:call_end]
new_block = doc_call + '''    coverage_gap = documents.get("coverage_gap")\n    if coverage_gap:\n        _warn(\n            warnings,\n            code=coverage_gap.get("code", "DOCUMENT_COVERAGE_GAP"),\n            message=coverage_gap.get("message", "Cobertura documental incompleta."),\n            gate=coverage_gap.get("gate"),\n        )\n    # F2.1C separa artefatos revogáveis dos que exigem intervenção manual.\n    # Somente blockers reais impedem preparação; documentos revogáveis entram\n    # no plano da futura saga.\n    warnings.extend(documents.get("warnings") or [])\n    blockers.extend(documents.get("blockers") or [])\n\n'''
text = text[:block_start] + new_block + text[block_end:]

needle = '        "document_counts": documents["tracked_counts"],\n'
if needle not in text:
    raise SystemExit('document_counts anchor not found')
text = text.replace(
    needle,
    needle + '        "document_inventory_digest": documents.get("inventory_digest"),\n',
    1,
)

p.write_text(text, encoding='utf-8')
