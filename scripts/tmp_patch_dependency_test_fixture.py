from pathlib import Path

path = Path('backend/tests/test_student_dependencies.py')
text = path.read_text(encoding='utf-8')

old_classes = '''    db.classes = MagicMock()\n    db.classes.find = MagicMock(return_value=classes_cursor)\n    courses_cursor = MagicMock()\n'''
new_classes = '''    db.classes = MagicMock()\n    db.classes.find = MagicMock(return_value=classes_cursor)\n    db.classes.find_one = AsyncMock(return_value={\n        "id": "cl-1",\n        "school_id": "sch-1",\n        "mantenedora_id": "mant-1",\n        "course_ids": ["co-1"],\n        "is_multi_grade": False,\n        "series": [],\n        "grade_level": "6º ANO",\n    })\n    courses_cursor = MagicMock()\n'''
if text.count(old_classes) != 1:
    raise SystemExit(f'classes fixture anchor count={text.count(old_classes)}')
text = text.replace(old_classes, new_classes, 1)

old_courses = '''    db.courses = MagicMock()\n    db.courses.find = MagicMock(return_value=courses_cursor)\n    return db\n'''
new_courses = '''    db.courses = MagicMock()\n    db.courses.find = MagicMock(return_value=courses_cursor)\n    db.courses.find_one = AsyncMock(return_value={\n        "id": "co-1",\n        "mantenedora_id": "mant-1",\n        "grade_levels": ["6º ANO"],\n    })\n    assignment_cursor = MagicMock()\n    assignment_cursor.__aiter__.return_value = []\n    db.teacher_assignments = MagicMock()\n    db.teacher_assignments.find = MagicMock(return_value=assignment_cursor)\n    return db\n'''
if text.count(old_courses) != 1:
    raise SystemExit(f'courses fixture anchor count={text.count(old_courses)}')
text = text.replace(old_courses, new_courses, 1)

path.write_text(text, encoding='utf-8')
print('DEPENDENCY_TEST_FIXTURE_PATCHED')
