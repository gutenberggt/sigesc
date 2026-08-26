# Normalização Global de Horários — 1º ao 5º ano — Inventário

## Política aprovada para análise

Ano letivo: **2026**.

### Turno matutino
- 1ª Aula: **07:00–07:55**
- 2ª Aula: **07:55–08:50**
- 3ª Aula: **09:10–10:05**
- 4ª Aula: **10:05–11:00**

### Turno vespertino
- 1ª Aula: **13:00–13:55**
- 2ª Aula: **13:55–14:50**
- 3ª Aula: **15:10–16:05**
- 4ª Aula: **16:05–17:00**

## Escopo

Todas as turmas de 1º ao 5º ano, incluindo multisseriadas e independentemente de já possuírem ou não horário cadastrado.

## Etapa atual

Somente inventário **READ-ONLY**. Nenhuma escrita em `class_schedules` é autorizada por este PR.

O inventário identifica explicitamente:
- turmas matutinas e vespertinas;
- turmas regulares e multisseriadas;
- horários existentes e ausentes;
- múltiplos horários para a mesma turma/ano;
- slots acima da 4ª aula;
- multisseriadas que cruzem o limite do 5º para o 6º ano;
- turnos sem política definida (`full_time`, `evening` ou outros).

Casos ambíguos são classificados como `BLOCKED_REQUIRES_REVIEW`, sem exclusão silenciosa do escopo e sem mutação.
