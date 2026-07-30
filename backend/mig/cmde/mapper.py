"""
CmdeMapper — tradução de aluno/escola SIGESC → linha de mapeamento CMDE.

Isola a montagem do payload. Reproduz exatamente a estrutura de GET /mec/students/mapping.
"""
from mig.cmde import validators


class CmdeMapper:
    @staticmethod
    def build_mapping_row(student: dict, school: dict) -> dict:
        school = school or {}
        base = {
            "id": student["id"],
            "full_name": student["full_name"],
            "cpf": student.get("cpf", ""),
            "nis": student.get("nis", ""),
            "inep_code": student.get("inep_code", ""),
            "school_name": school.get("name", ""),
            "school_inep": school.get("inep_code", ""),
        }
        base["ready"] = validators.is_ready(base)
        base["missing_fields"] = validators.missing_fields(base)
        return base
