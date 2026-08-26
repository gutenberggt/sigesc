# Enrollment Number Writer Guard

`enrollment_number` é identidade institucional e não pode ganhar novos escritores ad hoc.

O CI executa `.github/scripts/enrollment_number_writer_guard.py` dentro do check obrigatório `Backend - ruff lint`. O guard inventaria escritores por arquivo, função, coleção, primitiva Mongo e quantidade esperada. Qualquer escritor novo ou expansão da superfície existente falha o check.

Os escritores ainda existentes em `backend/routers/students.py` e o write-on-read de `backend/routers/documents.py::_ensure_enrollment_number` são dívida legada **congelada**, não padrão arquitetural autorizado. Novos fluxos devem usar o serviço canônico de matrículas ou um reconciliador governado com gates explícitos.

A edição genérica de uma matrícula não pode persistir `enrollment_number`.
