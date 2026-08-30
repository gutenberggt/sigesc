# P0 #250 — Fase 2.2.1 — falso erro após carregar Promoção

Data: 2026-08-30

## Evidência visual pós-deploy

Após o deploy da Fase 2.2, o caso-canário passou a exibir as notas na tela de Promoção, confirmando que a projeção via `/grades/by-class/{class_id}/{course_id}` chegou ao frontend. Entretanto, a interface também exibia o toast `Erro ao carregar dados de promoção`.

## Causa raiz

A Fase 2.2 moveu `allGrades` para dentro do ramo de gestão (`else`) porque o professor passou a usar `gradesByStudent`, alimentado pelas respostas `by-class`.

Ao final de `loadPromotionData`, permaneceu a linha legada:

`setGradesData(allGrades.flat());`

No perfil professor, `allGrades` não existe nesse escopo. A exceção ocorre **depois** de `setPromotionData(processed)`, por isso a tabela aparece corretamente e, em seguida, o `catch` mostra o toast de erro.

## Correção

A finalização passa a derivar a lista achatada da estrutura comum aos dois ramos:

`Array.from(gradesByStudent.values()).flat()`

Assim:

- professor e gestão usam a mesma fonte normalizada na etapa final;
- nenhuma nota é alterada;
- nenhum endpoint é alterado;
- nenhum RBAC é ampliado;
- nenhuma mutação de banco é realizada;
- o falso toast deixa de ser disparado pelo `ReferenceError` de `allGrades`.

## Regressão

O workflow `P0 #250 F2.2.1 Promotion false-toast Guard` falha se a referência legada `setGradesData(allGrades.flat())` reaparecer ou se a ordem de finalização deixar de usar `gradesByStudent` antes do `catch`.

## Publicação

Mudança funcional de frontend. Merge e deploy continuam sujeitos a autorização humana explícita.
