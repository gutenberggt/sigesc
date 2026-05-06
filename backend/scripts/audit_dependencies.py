"""
Audita imports DIRETOS do código (top-level apenas). Os pacotes não listados
aqui são dependências transitivas e devem permanecer em requirements.txt.

Uso: cd /app/backend && python scripts/audit_dependencies.py
"""
import ast
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXCLUDE = {'__pycache__', 'tests', '.venv', 'node_modules'}

# Mapa de nomes de import → pacotes pip
IMPORT_TO_PIP = {
    'jwt': 'PyJWT',
    'dotenv': 'python-dotenv',
    'multipart': 'python-multipart',
    'jose': 'python-jose',
    'PIL': 'Pillow',
    'bs4': 'beautifulsoup4',
    'spellchecker': 'pyspellchecker',
    'yaml': 'PyYAML',
    'pytest_asyncio': 'pytest-asyncio',
    'mongomock_motor': 'mongomock-motor',
    'dateutil': 'python-dateutil',
}

direct_imports = set()

for py_file in BACKEND_DIR.rglob('*.py'):
    if any(part in EXCLUDE for part in py_file.parts):
        continue
    if py_file.name.startswith('test_'):
        continue
    try:
        tree = ast.parse(py_file.read_text(encoding='utf-8'))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split('.')[0]
                direct_imports.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                top = node.module.split('.')[0]
                direct_imports.add(top)

# Filtra módulos do próprio projeto (estão em /app/backend)
local_modules = {p.stem for p in BACKEND_DIR.iterdir() if p.is_file() and p.suffix == '.py'}
local_modules |= {p.name for p in BACKEND_DIR.iterdir() if p.is_dir() and not p.name.startswith('.')}
external = direct_imports - local_modules - {'__future__'}

# Classifica como stdlib (heurística simples)
import sysconfig
stdlib_path = Path(sysconfig.get_paths()['stdlib'])
stdlib_modules = {p.stem for p in stdlib_path.glob('*.py')}
stdlib_modules |= {p.name for p in stdlib_path.iterdir() if p.is_dir()}

third_party = sorted(external - stdlib_modules)

print(f'=== Imports diretos de terceiros ({len(third_party)}) ===')
for name in third_party:
    pip_name = IMPORT_TO_PIP.get(name, name)
    print(f'  {name:<30} → pip install {pip_name}')

print()
print('Para gerar requirements minimal:')
print('  cd /app/backend && pip install pipreqs && pipreqs --force .')
print()
print('NOTA: Dependências transitivas (puxadas por pacotes diretos) NÃO aparecem aqui.')
print('Não remova pacotes do requirements.txt sem testar primeiro!')
