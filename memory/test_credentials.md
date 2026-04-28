# Credenciais de Teste - SIGESC

## Admin
- Email: gutenberg@sigesc.com
- Senha: @Celta2007

## Coordenador
- Email: coordenador@sigesc.com
- Senha: coordenador123

## Secretario
- Email: secretario@sigesc.com
- Senha: secretario123

## Agente de Vacinas
- Email: vacinas@sigesc.com
- Senha: vacinas123

## Assistência Social 2
- Email: assistencia2@sigesc.com
- Senha: assistencia2123

## Super Admin (Multi-Tenant)
- Email: gutenberg@sigesc.com (promovido automaticamente de admin → super_admin)
- Senha: @Celta2007
- Poderes: criar mantenedoras, designar gerentes, alternar contexto de tenant

## Aluno (Boletim Virtual)
- Email: aluno@sigesc.com
- Senha: aluno123
- Role: aluno
- Observação: vínculo `student_id` é atribuído via script `python backend/scripts/seed_test_student.py`.
  O script escolhe automaticamente um aluno com dados (matrícula/notas) e sincroniza o vínculo.
  Para re-rodar (idempotente): `cd /app/backend && python scripts/seed_test_student.py`

## Professor (QA AEE)
- Email: professor.teste@sigesc.com
- Senha: Professor@2026
- Role: professor (sem lotação override → role efetivo = professor)
- Mantenedora: SEMED (a991c1ac-56b1-46a8-b122-effedbe19b21)
- Escola vinculada: ESCOLA TESTE MULTISSERIADA (220d4022-ec5e-4fb6-86fc-9233112b87b2)
- Uso: validação do fluxo Diário AEE (criar Plano via modelo, salvar, gerar PDF).

## Professor (Ricleide)
- Email: ricleidegoncalves@gmail.com
- Senha: Professor@2026
- Role base: professor; lotação ativa em 2026 como `secretario` (role efetivo = secretario).
