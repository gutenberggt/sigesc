from pathlib import Path

path = Path('frontend/src/pages/LearningObjects.js')
text = path.read_text(encoding='utf-8')

old_import = "import { useNavigate } from 'react-router-dom';\n"
new_import = (
    "import { useNavigate } from 'react-router-dom';\n"
    "import { useDiaryPrefill } from '@/hooks/useDiaryPrefill';\n"
)
if text.count(old_import) != 1:
    raise SystemExit(f'import anchor inesperado: {text.count(old_import)}')
text = text.replace(old_import, new_import, 1)

old_anchor = "  const [availableClasses, setAvailableClasses] = useState([]);\n\n  // Carrega turmas do professor uma vez (para uso no modal de cópia)\n"
new_anchor = """  const [availableClasses, setAvailableClasses] = useState([]);

  useDiaryPrefill({
    schools,
    selectedSchool,
    setSelectedSchool,
    classes,
    selectedClass,
    setSelectedClass,
    courses,
    selectedCourse,
    setSelectedCourse,
    onCourseApplied: (courseId) => {
      setSelectedCourses((current) => current.length > 0 ? current : [courseId]);
    },
  });

  // Carrega turmas do professor uma vez (para uso no modal de cópia)
"""
if text.count(old_anchor) != 1:
    raise SystemExit(f'state anchor inesperado: {text.count(old_anchor)}')
text = text.replace(old_anchor, new_anchor, 1)

path.write_text(text, encoding='utf-8')
print('LearningObjects.js atualizado com prefill seguro.')
