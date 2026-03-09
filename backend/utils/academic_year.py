"""
Utilitários de verificação de ano letivo e bimestre.
Extraído de server.py durante a refatoração modular.
"""

from fastapi import HTTPException, status


def create_academic_year_validators(db):
    """
    Factory que cria as funções de validação de ano letivo vinculadas ao banco de dados.
    Retorna um dicionário com as funções prontas para uso.
    """

    async def check_academic_year_open(school_id: str, academic_year: int) -> bool:
        """Verifica se o ano letivo está aberto para uma escola específica."""
        school = await db.schools.find_one(
            {"id": school_id},
            {"_id": 0, "anos_letivos": 1}
        )
        if not school or not school.get('anos_letivos'):
            return True
        year_config = school['anos_letivos'].get(str(academic_year))
        if not year_config:
            return True
        return year_config.get('status', 'aberto') != 'fechado'

    async def verify_academic_year_open_or_raise(school_id: str, academic_year: int):
        """Verifica se o ano letivo está aberto e lança exceção se estiver fechado."""
        is_open = await check_academic_year_open(school_id, academic_year)
        if not is_open:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"O ano letivo {academic_year} está fechado para esta escola. Não é possível fazer alterações."
            )

    async def check_bimestre_edit_deadline(academic_year: int, bimestre: int = None) -> dict:
        """Verifica se a data limite de edição do bimestre foi ultrapassada."""
        from datetime import date
        today = date.today().isoformat()

        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year},
            {"_id": 0}
        )
        if not calendario:
            return {"can_edit": True, "bimestre": None, "data_limite": None, "message": "Calendário letivo não configurado"}

        if bimestre:
            data_limite = calendario.get(f"bimestre_{bimestre}_data_limite")
            if not data_limite:
                return {"can_edit": True, "bimestre": bimestre, "data_limite": None, "message": f"Data limite do {bimestre}º bimestre não configurada"}
            if today > data_limite:
                return {
                    "can_edit": False,
                    "bimestre": bimestre,
                    "data_limite": data_limite,
                    "message": f"O prazo para edição do {bimestre}º bimestre encerrou em {data_limite}"
                }
            return {"can_edit": True, "bimestre": bimestre, "data_limite": data_limite, "message": "Dentro do prazo"}

        for i in range(1, 5):
            inicio = calendario.get(f"bimestre_{i}_inicio")
            fim = calendario.get(f"bimestre_{i}_fim")
            data_limite = calendario.get(f"bimestre_{i}_data_limite")
            if inicio and fim and today >= inicio and today <= fim:
                if data_limite and today > data_limite:
                    return {
                        "can_edit": False,
                        "bimestre": i,
                        "data_limite": data_limite,
                        "message": f"O prazo para edição do {i}º bimestre encerrou em {data_limite}"
                    }
                return {"can_edit": True, "bimestre": i, "data_limite": data_limite, "message": "Dentro do prazo"}

        return {"can_edit": True, "bimestre": None, "data_limite": None, "message": "Fora do período letivo"}

    async def verify_bimestre_edit_deadline_or_raise(academic_year: int, bimestre: int, user_role: str):
        """Verifica se pode editar notas/frequência do bimestre e lança exceção se não puder."""
        if user_role in ['admin', 'secretario']:
            return True
        check = await check_bimestre_edit_deadline(academic_year, bimestre)
        if not check["can_edit"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=check["message"]
            )
        return True

    return {
        'check_academic_year_open': check_academic_year_open,
        'verify_academic_year_open_or_raise': verify_academic_year_open_or_raise,
        'check_bimestre_edit_deadline': check_bimestre_edit_deadline,
        'verify_bimestre_edit_deadline_or_raise': verify_bimestre_edit_deadline_or_raise,
    }
