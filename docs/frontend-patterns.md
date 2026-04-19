# Frontend Patterns — SIGESC

Guia prático para páginas grandes (≥ 800 linhas) com múltiplas abas/filtros. Baseado nas refatorações feitas em `Attendance.js` e `Grades.js`.

---

## Quando aplicar este padrão

Use quando uma página apresentar ≥ 2 dos sintomas:

- Arquivo `.js` da página > 800 linhas
- Mesmo componente renderiza múltiplas abas/modos (ex: "Por Turma" / "Por Aluno")
- Muitos `useState` (> 20) compartilhados entre seções
- Props drilling explícito (> 10 props passadas para sub-componentes)
- Fetches inline com `fetch()` ou `axios.get()` duplicando a camada de serviço
- Constantes de env (`process.env.REACT_APP_BACKEND_URL`) repetidas

---

## Estrutura alvo

```
src/
├── pages/
│   └── Attendance.js             # CONTAINER: estado, effects, handlers, UI de cabeçalho/modais
├── contexts/
│   └── AttendanceContext.js      # createContext + hook useAttendance()
├── components/attendance/
│   ├── LancamentoTab.jsx         # PRESENTATIONAL: consome useAttendance()
│   ├── RegistrosTab.jsx
│   ├── InformacoesTab.jsx
│   ├── RelatoriosTab.jsx
│   ├── AlertasTab.jsx
│   └── helpers.jsx               # (opcional) constantes, utilitários puros, sub-componentes
└── services/
    └── api.js                    # toda chamada HTTP vive aqui
```

---

## Passo a passo da refatoração

### 1. Inventariar o estado e os fetches

```bash
grep -c "const \[" src/pages/MinhaPagina.js           # conta useStates
grep -n "fetch(\|axios\." src/pages/MinhaPagina.js    # lista fetches inline
```

### 2. Migrar fetches inline para `services/api.js`

Antes:
```jsx
const token = localStorage.getItem('accessToken');
const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/foo/${id}`, {
  headers: { Authorization: `Bearer ${token}` }
});
const data = await res.json();
```

Depois (`services/api.js` já tem interceptor que anexa o token):
```jsx
export const fooAPI = {
  getById: async (id) => {
    const response = await axios.get(`${API}/foo/${id}`);
    return response.data;
  },
  getPdfBlob: async (id) => {
    const response = await axios.get(`${API}/foo/${id}/pdf`, { responseType: 'blob' });
    return response.data;
  }
};
```

Regras:
- Nunca use `fetch()` cru nas páginas — sempre o service.
- Para download de PDF/arquivo, use `{ responseType: 'blob' }` e retorne `response.data`.
- Remova constantes duplicadas tipo `const API_URL = process.env.REACT_APP_BACKEND_URL` da página — elas já estão no `api.js`.

### 3. Criar o Context

`src/contexts/MinhaPaginaContext.js`:

```js
import { createContext, useContext } from 'react';

export const MinhaPaginaContext = createContext(null);

export const useMinhaPagina = () => {
  const ctx = useContext(MinhaPaginaContext);
  if (!ctx) {
    throw new Error('useMinhaPagina must be used inside <MinhaPaginaContext.Provider>');
  }
  return ctx;
};
```

### 4. Extrair cada aba em arquivo próprio

- Um arquivo `.jsx` por aba em `components/minha-pagina/`.
- No topo, destructure **apenas** o que a aba precisa do contexto:

```jsx
import { useMinhaPagina } from '@/contexts/MinhaPaginaContext';

export const MinhaTab = () => {
  const { schools, selectedSchool, setSelectedSchool, loadData, data } = useMinhaPagina();
  return (
    <div data-testid="minha-tab">
      {/* JSX original, sem props */}
    </div>
  );
};
```

### 5. Container: lazy + Suspense + Provider

```jsx
import { useMemo, lazy, Suspense } from 'react';
import { MinhaPaginaContext } from '@/contexts/MinhaPaginaContext';

const TabA = lazy(() => import('@/components/minha-pagina/TabA').then(m => ({ default: m.TabA })));
const TabB = lazy(() => import('@/components/minha-pagina/TabB').then(m => ({ default: m.TabB })));

export default function MinhaPagina() {
  // ... todo estado/effects/handlers aqui

  const contextValue = useMemo(() => ({
    schools, selectedSchool, setSelectedSchool,
    loadData, data,
    // ... tudo que as abas consomem
  }), [schools, selectedSchool, data /* ... deps que mudam */]);

  return (
    <Layout>
      <MinhaPaginaContext.Provider value={contextValue}>
        <Suspense fallback={<LoadingSpinner data-testid="tab-loading" />}>
          {activeTab === 'a' && <TabA />}
          {activeTab === 'b' && <TabB />}
        </Suspense>
      </MinhaPaginaContext.Provider>
    </Layout>
  );
}
```

**Regras críticas:**

- **`useMemo` no value** — sem ele, todo re-render do container cria um objeto novo e força re-render em todas as abas.
- **Setters não entram nas deps** do `useMemo` (são estáveis por padrão no React).
- **Handlers criados com `useCallback`** devem entrar nas deps do `useMemo`.
- **Não misture props + context** na mesma aba — escolha um.

### 6. Extrair sub-componentes reutilizáveis

Se uma aba ainda tem > 300 linhas, procure blocos isolados (tabelas, badges de status, forms complexos) e extraia:

- `<GradesTable />` — a tabela de notas dentro da `TurmaTab` também consome `useGrades()` diretamente (sem props).
- `<StatusBadge status={...} />` — componente puro sem contexto, só props.

Heurística: se o sub-componente precisa de **≥ 3 campos do contexto**, deixe ele consumir o hook. Se precisa de **≤ 2 campos**, passe como props.

---

## Anti-padrões a evitar

❌ **Retornar JSX de função no contexto** — `renderStatus: (status) => <span>...</span>` é sintoma de que falta um componente. Extraia para `<StatusBadge />`.

❌ **Duplicar `process.env.REACT_APP_BACKEND_URL`** em vários lugares. Use `services/api.js`.

❌ **Colocar TODOS os estados no context** — se um estado é usado só no container (ex: modal de configurações), deixe ele local.

❌ **Misturar contexto com Redux/Zustand sem motivo** — para 1 página, Context + `useMemo` basta.

❌ **Esquecer `useMemo` no Provider value** — causa re-render em cascata.

❌ **Lazy load sem Suspense boundary** — quebra o rendering com o clássico "A component suspended while responding to synchronous input".

---

## Checklist antes de abrir PR

- [ ] Página principal < 1000 linhas
- [ ] Cada aba < 400 linhas
- [ ] Zero `fetch()` ou `axios.get()` inline nas páginas/abas
- [ ] Zero `process.env.REACT_APP_BACKEND_URL` fora de `api.js`
- [ ] Provider value envolto em `useMemo`
- [ ] Cada aba tem `data-testid="<pagina>-<tab>-tab"` no root
- [ ] ESLint limpo
- [ ] Testing agent validou fluxos end-to-end (não só smoke)

---

## Exemplos implementados

| Página          | Linhas antes | Linhas depois | Arquivos criados                                                                                |
|-----------------|--------------|---------------|-------------------------------------------------------------------------------------------------|
| `Attendance.js` | 2071         | ~1146         | `contexts/AttendanceContext.js`, `components/attendance/{Lancamento,Registros,Informacoes,Relatorios,Alertas}Tab.jsx` |
| `Grades.js`     | 1604         | ~835          | `contexts/GradesContext.js`, `components/grades/{TurmaTab,AlunoTab,GradesTable,gradeHelpers}.jsx` |

Refs: iterations 51–54 em `/app/test_reports/`.
