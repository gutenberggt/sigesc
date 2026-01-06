"""
Test cases for Bug P0: MANDATORY components without grades (media=None) should be REPROVADO

Bug Description:
- Students with MANDATORY components without grades (media=None) were being marked as APPROVED incorrectly
- The rule is: 'Only APPROVED if ALL mandatory components have average >= 5.0'
- If a mandatory component has no grade (media=None), the student CANNOT be approved

Test Case Reference:
- Student Ana Beatriz Pereira Sousa - 5º Ano A
- Has 2 components with grades (Língua Portuguesa 5.2, Arte 5.8)
- Has 10 components WITHOUT grades (media=None)
- Before fix: APROVADO (incorrect)
- After fix: REPROVADO (correct)

Fix Applied:
- In grade_calculator.py lines 446-448 (calcular_resultado_final_aluno):
  Mandatory components without grade are now added to componentes_reprovados
- In grade_calculator.py lines 802-806 (_calcular_resultado_com_avaliacao):
  Same fix applied

Additional Fix:
- In pdf_generator.py: Grades now use comma (,) instead of period (.) for display
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from grade_calculator import (
    calcular_resultado_final_aluno,
    _calcular_resultado_com_avaliacao,
    format_grade
)


class TestMandatoryNoGradeBugFix:
    """Tests for the mandatory component without grade bug fix - P0 priority"""
    
    def test_mandatory_component_without_grade_should_be_reprovado(self):
        """
        CRITICAL TEST: Student with mandatory component without grade should be REPROVADO
        This is the main bug that was fixed
        """
        # Scenario: 2 components with passing grades, 1 mandatory without grade
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 5.2, 'optativo': False},  # Passing
            {'nome': 'Arte', 'media': 5.8, 'optativo': False},               # Passing
            {'nome': 'Matemática', 'media': None, 'optativo': False},        # NO GRADE - MANDATORY
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0
        )
        
        # MUST be REPROVADO because Matemática has no grade
        assert resultado['resultado'] == 'REPROVADO', \
            f"Student with mandatory component without grade should be REPROVADO, got {resultado['resultado']}"
        assert 'Matemática' in resultado['componentes_reprovados'], \
            f"Matemática should be in failed components, got {resultado['componentes_reprovados']}"
        print(f"✅ Test passed: Mandatory without grade → REPROVADO (failed: {resultado['componentes_reprovados']})")
    
    def test_ana_beatriz_scenario_10_components_without_grade(self):
        """
        Real scenario: Ana Beatriz Pereira Sousa - 5º Ano A
        - 2 components with grades (Língua Portuguesa 5.2, Arte 5.8)
        - 10 components WITHOUT grades
        - Should be REPROVADO
        """
        medias_por_componente = [
            # Components WITH grades (passing)
            {'nome': 'Língua Portuguesa', 'media': 5.2, 'optativo': False},
            {'nome': 'Arte', 'media': 5.8, 'optativo': False},
            # Components WITHOUT grades (mandatory)
            {'nome': 'Matemática', 'media': None, 'optativo': False},
            {'nome': 'Ciências', 'media': None, 'optativo': False},
            {'nome': 'História', 'media': None, 'optativo': False},
            {'nome': 'Geografia', 'media': None, 'optativo': False},
            {'nome': 'Educação Física', 'media': None, 'optativo': False},
            {'nome': 'Ensino Religioso', 'media': None, 'optativo': False},
            {'nome': 'Educação Ambiental e Clima', 'media': None, 'optativo': False},
            {'nome': 'Arte e Cultura', 'media': None, 'optativo': False},
            {'nome': 'Recreação, Esporte e Lazer', 'media': None, 'optativo': False},
            {'nome': 'Tecnologia e Informática', 'media': None, 'optativo': False},
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0,
            nivel_ensino='fundamental_anos_iniciais',
            grade_level='5º Ano'
        )
        
        # MUST be REPROVADO because 10 mandatory components have no grade
        assert resultado['resultado'] == 'REPROVADO', \
            f"Ana Beatriz should be REPROVADO with 10 components without grade, got {resultado['resultado']}"
        assert len(resultado['componentes_reprovados']) == 10, \
            f"Should have 10 failed components, got {len(resultado['componentes_reprovados'])}"
        print(f"✅ Test passed: Ana Beatriz scenario → REPROVADO (10 components without grade)")
        print(f"   Failed components: {resultado['componentes_reprovados']}")
    
    def test_optional_without_grade_should_be_ignored(self):
        """
        OPTIONAL components without grade should be IGNORED (not count for approval or failure)
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 6.0, 'optativo': False},  # Passing
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},         # Passing
            {'nome': 'Inglês', 'media': None, 'optativo': True},             # NO GRADE - OPTIONAL (should be ignored)
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0
        )
        
        # Should be APROVADO because optional without grade is ignored
        assert resultado['resultado'] == 'APROVADO', \
            f"Student should be APROVADO when optional has no grade, got {resultado['resultado']}"
        assert len(resultado['componentes_reprovados']) == 0, \
            f"Should have no failed components, got {resultado['componentes_reprovados']}"
        print(f"✅ Test passed: Optional without grade → IGNORED, student APROVADO")
    
    def test_all_mandatory_with_passing_grades_should_be_aprovado(self):
        """
        All mandatory components with grades >= 5.0 should result in APROVADO
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 5.0, 'optativo': False},
            {'nome': 'Matemática', 'media': 5.0, 'optativo': False},
            {'nome': 'Ciências', 'media': 5.0, 'optativo': False},
            {'nome': 'História', 'media': 5.0, 'optativo': False},
            {'nome': 'Geografia', 'media': 5.0, 'optativo': False},
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0
        )
        
        assert resultado['resultado'] == 'APROVADO', \
            f"Student with all passing grades should be APROVADO, got {resultado['resultado']}"
        assert len(resultado['componentes_reprovados']) == 0, \
            "Should have no failed components"
        print(f"✅ Test passed: All mandatory >= 5.0 → APROVADO")


class TestCalcResultadoComAvaliacaoMandatoryNoGrade:
    """Tests for _calcular_resultado_com_avaliacao with mandatory components without grade"""
    
    def test_mandatory_without_grade_should_fail(self):
        """Mandatory component without grade should be marked as failed"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': None, 'optativo': False},  # NO GRADE - MANDATORY
            {'nome': 'Português', 'media': 6.0, 'optativo': False},    # Passing
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
        }
        
        resultado = _calcular_resultado_com_avaliacao(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            frequencia_aluno=80.0,
            permite_dependencia=False,
            is_serie_final=False
        )
        
        assert resultado['resultado'] == 'REPROVADO', \
            f"Should be REPROVADO with mandatory without grade, got {resultado['resultado']}"
        assert 'Matemática' in resultado['detalhes'], \
            "Matemática should be mentioned in details"
        print(f"✅ Test passed: _calcular_resultado_com_avaliacao mandatory without grade → REPROVADO")
    
    def test_optional_without_grade_should_be_ignored(self):
        """Optional component without grade should be ignored"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},   # Passing
            {'nome': 'Português', 'media': 6.0, 'optativo': False},    # Passing
            {'nome': 'Inglês', 'media': None, 'optativo': True},       # NO GRADE - OPTIONAL (ignored)
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
        }
        
        resultado = _calcular_resultado_com_avaliacao(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            frequencia_aluno=80.0,
            permite_dependencia=False,
            is_serie_final=False
        )
        
        assert resultado['resultado'] == 'APROVADO', \
            f"Should be APROVADO when optional has no grade, got {resultado['resultado']}"
        print(f"✅ Test passed: _calcular_resultado_com_avaliacao optional without grade → IGNORED")


class TestMixedScenarios:
    """Tests for mixed scenarios with mandatory/optional and with/without grades"""
    
    def test_mix_mandatory_with_and_without_grades(self):
        """
        Mix of mandatory components: some with passing grades, some without grades
        Should be REPROVADO because of mandatory without grade
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 8.0, 'optativo': False},  # Passing
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},         # Passing
            {'nome': 'Ciências', 'media': None, 'optativo': False},          # NO GRADE - MANDATORY
            {'nome': 'História', 'media': 6.0, 'optativo': False},           # Passing
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0
        )
        
        assert resultado['resultado'] == 'REPROVADO', \
            f"Should be REPROVADO with mandatory without grade, got {resultado['resultado']}"
        assert 'Ciências' in resultado['componentes_reprovados'], \
            "Ciências should be in failed components"
        assert len(resultado['componentes_reprovados']) == 1, \
            f"Should have exactly 1 failed component, got {len(resultado['componentes_reprovados'])}"
        print(f"✅ Test passed: Mix mandatory with/without grades → REPROVADO")
    
    def test_mandatory_failing_and_without_grade(self):
        """
        Mandatory components: some failing (< 5.0), some without grades
        Both should count as failed
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 8.0, 'optativo': False},  # Passing
            {'nome': 'Matemática', 'media': 3.0, 'optativo': False},         # FAILING (< 5.0)
            {'nome': 'Ciências', 'media': None, 'optativo': False},          # NO GRADE - MANDATORY
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0
        )
        
        assert resultado['resultado'] == 'REPROVADO', \
            f"Should be REPROVADO, got {resultado['resultado']}"
        assert 'Matemática' in resultado['componentes_reprovados'], \
            "Matemática should be in failed components"
        assert 'Ciências' in resultado['componentes_reprovados'], \
            "Ciências should be in failed components"
        assert len(resultado['componentes_reprovados']) == 2, \
            f"Should have 2 failed components, got {len(resultado['componentes_reprovados'])}"
        print(f"✅ Test passed: Mandatory failing + without grade → both count as failed")
    
    def test_optional_with_failing_grade_should_count(self):
        """
        Optional component WITH a failing grade (< 5.0) should count as failed
        (Different from optional WITHOUT grade which is ignored)
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 8.0, 'optativo': False},  # Passing
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},         # Passing
            {'nome': 'Inglês', 'media': 3.0, 'optativo': True},              # FAILING - OPTIONAL (should count!)
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0
        )
        
        # Optional WITH grade should count - student should be REPROVADO
        assert resultado['resultado'] == 'REPROVADO', \
            f"Optional with failing grade should count, got {resultado['resultado']}"
        assert 'Inglês' in resultado['componentes_reprovados'], \
            "Inglês should be in failed components"
        print(f"✅ Test passed: Optional with failing grade → counts as failed")


class TestGradeFormatting:
    """Tests for grade formatting with comma instead of period"""
    
    def test_format_grade_uses_comma(self):
        """Grade formatting should use comma (,) instead of period (.)"""
        # Test the format_grade function from grade_calculator.py
        result = format_grade(5.2)
        assert ',' in result, f"Grade should use comma, got {result}"
        assert '.' not in result, f"Grade should not use period, got {result}"
        assert result == '5,2', f"Expected '5,2', got {result}"
        print(f"✅ Test passed: format_grade(5.2) = '{result}'")
    
    def test_format_grade_various_values(self):
        """Test format_grade with various values"""
        test_cases = [
            (5.0, '5,0'),
            (7.5, '7,5'),
            (10.0, '10,0'),
            (0.0, '0,0'),
            (4.9, '4,9'),
            (None, '-'),
        ]
        
        for value, expected in test_cases:
            result = format_grade(value)
            assert result == expected, f"format_grade({value}) should be '{expected}', got '{result}'"
        
        print(f"✅ Test passed: format_grade uses comma for all values")


class TestAnosIniciaisNoGrade:
    """Tests specific to Anos Iniciais (3º ao 5º Ano) with mandatory components without grade"""
    
    def test_5_ano_mandatory_without_grade_reprovado(self):
        """
        5º Ano: Mandatory component without grade should result in REPROVADO
        Anos Iniciais does not allow dependency
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 5.2, 'optativo': False},
            {'nome': 'Arte', 'media': 5.8, 'optativo': False},
            {'nome': 'Matemática', 'media': None, 'optativo': False},  # NO GRADE
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': True,  # Even if enabled, Anos Iniciais ignores
            'max_componentes_dependencia': 2,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0,
            nivel_ensino='fundamental_anos_iniciais',
            grade_level='5º Ano'
        )
        
        # Anos Iniciais should be REPROVADO (no dependency allowed)
        assert resultado['resultado'] == 'REPROVADO', \
            f"5º Ano with mandatory without grade should be REPROVADO, got {resultado['resultado']}"
        print(f"✅ Test passed: 5º Ano mandatory without grade → REPROVADO")
    
    def test_3_ano_all_mandatory_with_grades_aprovado(self):
        """
        3º Ano: All mandatory components with passing grades should be APROVADO
        """
        medias_por_componente = [
            {'nome': 'Língua Portuguesa', 'media': 6.0, 'optativo': False},
            {'nome': 'Matemática', 'media': 5.5, 'optativo': False},
            {'nome': 'Ciências', 'media': 7.0, 'optativo': False},
            {'nome': 'História', 'media': 5.0, 'optativo': False},
            {'nome': 'Geografia', 'media': 6.5, 'optativo': False},
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0,
            nivel_ensino='fundamental_anos_iniciais',
            grade_level='3º Ano'
        )
        
        assert resultado['resultado'] == 'APROVADO', \
            f"3º Ano with all passing grades should be APROVADO, got {resultado['resultado']}"
        print(f"✅ Test passed: 3º Ano all mandatory with grades → APROVADO")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
