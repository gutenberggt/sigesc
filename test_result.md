# Test Results

## Current Testing Focus
Testing Sistema de Notas (Fase 4) - Lançamento de Notas

## Test Scenarios

### Scenario 1: Grades Page - Filter Components by Class
- **Objective**: Verify that when selecting a school, class, and the component dropdown shows only relevant curriculum components based on the class's education level
- **URL**: /admin/grades
- **Steps**:
  1. Login with admin@sigesc.com / password
  2. Navigate to /admin/grades
  3. Select school "EMEIEF SORRISO DO ARAGUAIA"
  4. Select class "3º Ano A - 3º Ano" (education_level: fundamental_anos_iniciais)
  5. Check if Component dropdown shows curriculum components for fundamental_anos_iniciais level
- **Expected**: Component dropdown should show 9 components (Matemática, Língua Portuguesa, Arte, Educação Física, Ciências, História, Geografia, Ensino Religioso, Educação Ambiental e Clima)

### Scenario 2: Load Grades for Class
- **Objective**: Verify grades can be loaded for a class/component combination
- **Steps**:
  1. After selecting school, class, and component
  2. Click "Carregar Notas" button
- **Expected**: Should show table with student grades or empty message if no students

### Scenario 3: API Endpoint Test - Courses
- **Objective**: Verify courses API returns data with nivel_ensino filter
- **API**: GET /api/courses
- **Expected**: Returns courses with school_id (optional), nivel_ensino, grade_levels fields

## Credentials
- Admin: admin@sigesc.com / password
- SEMED (readonly): semed@sigesc.com / password

## Previous Test Results
- ✅ Backend Grades API (all endpoints working)
- ✅ Grade calculation formula verified
- ✅ Recovery system working
- ✅ SEMED role permissions working

## Incorporate User Feedback
- Focus on testing the component filtering based on education level and grade level
- Test both "Por Turma" and "Por Aluno" tabs if time permits
