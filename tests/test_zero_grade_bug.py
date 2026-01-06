"""
Test cases for Bug P0: Students with 0.0 average being incorrectly marked as APPROVED

Bug Description:
- Students with average 0.0 in curricular components were being marked as APPROVED incorrectly
- The cause was that the code set media=None when total_pontos == 0, causing components 
  with 0.0 average to be ignored in the approval verification

Fix Applied:
- In pdf_generator.py line 828-831: Now uses has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
  to check if there's any grade registered, and only sets media=None when there are no grades at all

Test Scenarios:
1. Student with all grades 0 should be REPROVADO (not APROVADO)
2. Student with some grades 0 and some None should have correct average calculation
3. Student with all grades None should be EM ANDAMENTO (no grades registered)
4. Student with average exactly 5.0 should be APROVADO
5. Student with average 4.9 should be REPROVADO
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, '/app/backend')

from grade_calculator import (
    calculate_weighted_average,
    calcular_resultado_final_aluno,
    _calcular_resultado_com_avaliacao,
    determine_status,
    MIN_AVERAGE
)


class TestZeroGradeBugFix:
    """Tests for the zero grade bug fix - P0 priority"""
    
    def test_all_grades_zero_should_be_reprovado(self):
        """
        CRITICAL TEST: Student with all grades 0 should be REPROVADO, not APROVADO
        This is the main bug that was fixed
        """
        # Scenario: All bimester grades are 0
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},
            {'nome': 'Português', 'media': 0.0, 'optativo': False},
            {'nome': 'Ciências', 'media': 0.0, 'optativo': False},
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
            frequencia_aluno=80.0  # Good attendance
        )
        
        # MUST be REPROVADO, not APROVADO
        assert resultado['resultado'] == 'REPROVADO', \
            f"Student with all grades 0.0 should be REPROVADO, got {resultado['resultado']}"
        assert len(resultado['componentes_reprovados']) == 3, \
            f"Should have 3 failed components, got {len(resultado['componentes_reprovados'])}"
        print(f"✅ Test passed: All grades 0 → REPROVADO (components: {resultado['componentes_reprovados']})")
    
    def test_single_component_zero_should_be_reprovado(self):
        """Student with one component at 0.0 and others passing should be REPROVADO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},  # Failed
            {'nome': 'Português', 'media': 7.0, 'optativo': False},   # Passed
            {'nome': 'Ciências', 'media': 8.0, 'optativo': False},    # Passed
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
            f"Student with one component at 0.0 should be REPROVADO, got {resultado['resultado']}"
        assert 'Matemática' in resultado['componentes_reprovados'], \
            "Matemática should be in failed components"
        print(f"✅ Test passed: Single component 0 → REPROVADO (failed: {resultado['componentes_reprovados']})")
    
    def test_all_grades_none_should_be_em_andamento(self):
        """Student with no grades registered should be EM ANDAMENTO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': None, 'optativo': False},
            {'nome': 'Português', 'media': None, 'optativo': False},
            {'nome': 'Ciências', 'media': None, 'optativo': False},
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
        
        assert resultado['resultado'] == 'EM ANDAMENTO', \
            f"Student with no grades should be EM ANDAMENTO, got {resultado['resultado']}"
        print(f"✅ Test passed: All grades None → EM ANDAMENTO")
    
    def test_average_exactly_5_should_be_aprovado(self):
        """Student with average exactly 5.0 should be APROVADO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 5.0, 'optativo': False},
            {'nome': 'Português', 'media': 5.0, 'optativo': False},
            {'nome': 'Ciências', 'media': 5.0, 'optativo': False},
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
            f"Student with average 5.0 should be APROVADO, got {resultado['resultado']}"
        assert len(resultado['componentes_reprovados']) == 0, \
            "Should have no failed components"
        print(f"✅ Test passed: Average 5.0 → APROVADO")
    
    def test_average_4_9_should_be_reprovado(self):
        """Student with average 4.9 should be REPROVADO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 4.9, 'optativo': False},
            {'nome': 'Português', 'media': 4.9, 'optativo': False},
            {'nome': 'Ciências', 'media': 4.9, 'optativo': False},
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
            f"Student with average 4.9 should be REPROVADO, got {resultado['resultado']}"
        assert len(resultado['componentes_reprovados']) == 3, \
            "Should have 3 failed components"
        print(f"✅ Test passed: Average 4.9 → REPROVADO")


class TestCalcResultadoComAvaliacao:
    """Tests for _calcular_resultado_com_avaliacao function"""
    
    def test_zero_average_component_should_fail(self):
        """Component with 0.0 average should be marked as failed"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},
            {'nome': 'Português', 'media': 6.0, 'optativo': False},
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
            f"Should be REPROVADO with 0.0 component, got {resultado['resultado']}"
        assert 'Matemática' in resultado['detalhes'], \
            "Matemática should be mentioned in details"
        print(f"✅ Test passed: _calcular_resultado_com_avaliacao with 0.0 → REPROVADO")
    
    def test_all_passing_should_be_aprovado(self):
        """All components passing should result in APROVADO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},
            {'nome': 'Português', 'media': 6.0, 'optativo': False},
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
            f"Should be APROVADO with all passing, got {resultado['resultado']}"
        print(f"✅ Test passed: All passing → APROVADO")


class TestWeightedAverageCalculation:
    """Tests for calculate_weighted_average function"""
    
    def test_all_zeros_should_return_zero_average(self):
        """All grades 0 should return average 0.0, not None"""
        average, details = calculate_weighted_average(
            b1=0, b2=0, b3=0, b4=0
        )
        
        assert average == 0.0, f"Average should be 0.0, got {average}"
        print(f"✅ Test passed: All zeros → average 0.0")
    
    def test_all_none_should_return_zero_average(self):
        """All None grades should return average 0.0 (None treated as 0)"""
        average, details = calculate_weighted_average(
            b1=None, b2=None, b3=None, b4=None
        )
        
        # According to the code, None is treated as 0 for calculation
        assert average == 0.0, f"Average should be 0.0 when all None, got {average}"
        print(f"✅ Test passed: All None → average 0.0")
    
    def test_weighted_formula_correct(self):
        """Test the weighted formula: (B1×2 + B2×3 + B3×2 + B4×3) / 10"""
        # B1=10, B2=10, B3=10, B4=10 → (10×2 + 10×3 + 10×2 + 10×3) / 10 = 100/10 = 10.0
        average, details = calculate_weighted_average(
            b1=10, b2=10, b3=10, b4=10
        )
        assert average == 10.0, f"Average should be 10.0, got {average}"
        
        # B1=5, B2=5, B3=5, B4=5 → (5×2 + 5×3 + 5×2 + 5×3) / 10 = 50/10 = 5.0
        average, details = calculate_weighted_average(
            b1=5, b2=5, b3=5, b4=5
        )
        assert average == 5.0, f"Average should be 5.0, got {average}"
        
        # B1=0, B2=0, B3=0, B4=0 → (0×2 + 0×3 + 0×2 + 0×3) / 10 = 0/10 = 0.0
        average, details = calculate_weighted_average(
            b1=0, b2=0, b3=0, b4=0
        )
        assert average == 0.0, f"Average should be 0.0, got {average}"
        
        print(f"✅ Test passed: Weighted formula calculation correct")


class TestDetermineStatus:
    """Tests for determine_status function"""
    
    def test_zero_average_should_be_reprovado_nota(self):
        """Average 0.0 should return reprovado_nota status"""
        status = determine_status(average=0.0, attendance_percentage=80.0)
        assert status == 'reprovado_nota', f"Status should be reprovado_nota, got {status}"
        print(f"✅ Test passed: Average 0.0 → reprovado_nota")
    
    def test_none_average_should_be_cursando(self):
        """None average should return cursando status"""
        status = determine_status(average=None, attendance_percentage=80.0)
        assert status == 'cursando', f"Status should be cursando, got {status}"
        print(f"✅ Test passed: Average None → cursando")
    
    def test_passing_average_should_be_aprovado(self):
        """Average >= 5.0 should return aprovado status"""
        status = determine_status(average=5.0, attendance_percentage=80.0)
        assert status == 'aprovado', f"Status should be aprovado, got {status}"
        
        status = determine_status(average=7.5, attendance_percentage=80.0)
        assert status == 'aprovado', f"Status should be aprovado, got {status}"
        print(f"✅ Test passed: Passing average → aprovado")


class TestApprovalRulesByEducationLevel:
    """Tests for approval rules by education level (Anos Iniciais, Anos Finais, 9º Ano, EJA)"""
    
    def test_anos_iniciais_no_dependency(self):
        """Anos Iniciais should not allow dependency - only APROVADO or REPROVADO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},
            {'nome': 'Português', 'media': 7.0, 'optativo': False},
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': True,  # Even if enabled
            'max_componentes_dependencia': 2,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0,
            nivel_ensino='fundamental_anos_iniciais',  # Anos Iniciais
            grade_level='3º Ano'
        )
        
        # Anos Iniciais should be REPROVADO, not APROVADO COM DEPENDÊNCIA
        assert resultado['resultado'] == 'REPROVADO', \
            f"Anos Iniciais should be REPROVADO (no dependency), got {resultado['resultado']}"
        print(f"✅ Test passed: Anos Iniciais with 0.0 → REPROVADO (no dependency)")
    
    def test_9_ano_no_aprovado_com_dependencia(self):
        """9º Ano should not allow APROVADO COM DEPENDÊNCIA - only EM DEPENDÊNCIA or REPROVADO"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},
            {'nome': 'Português', 'media': 7.0, 'optativo': False},
        ]
        
        regras_aprovacao = {
            'media_aprovacao': 5.0,
            'frequencia_minima': 75.0,
            'aprovacao_com_dependencia': True,
            'max_componentes_dependencia': 2,
            'cursar_apenas_dependencia': False,
        }
        
        resultado = calcular_resultado_final_aluno(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            enrollment_status='active',
            is_educacao_infantil=False,
            frequencia_aluno=80.0,
            nivel_ensino='fundamental_anos_finais',
            grade_level='9º Ano'  # Final year
        )
        
        # 9º Ano should be REPROVADO (no APROVADO COM DEPENDÊNCIA for final year)
        assert resultado['resultado'] == 'REPROVADO', \
            f"9º Ano should be REPROVADO (no APROVADO COM DEPENDÊNCIA), got {resultado['resultado']}"
        print(f"✅ Test passed: 9º Ano with 0.0 → REPROVADO (no APROVADO COM DEPENDÊNCIA)")


class TestEdgeCases:
    """Edge case tests"""
    
    def test_mixed_zero_and_none_grades(self):
        """Test with mix of 0 and None grades"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},  # Explicit 0
            {'nome': 'Português', 'media': None, 'optativo': False},  # No grade
            {'nome': 'Ciências', 'media': 6.0, 'optativo': False},    # Passing
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
        
        # Should be REPROVADO because Matemática has 0.0
        assert resultado['resultado'] == 'REPROVADO', \
            f"Should be REPROVADO with 0.0 component, got {resultado['resultado']}"
        assert 'Matemática' in resultado['componentes_reprovados'], \
            "Matemática should be in failed components"
        print(f"✅ Test passed: Mixed 0 and None → REPROVADO (0.0 component fails)")
    
    def test_optional_component_with_zero_ignored(self):
        """Optional component with 0.0 should still count if it has a grade"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},
            {'nome': 'Português', 'media': 7.0, 'optativo': False},
            {'nome': 'Inglês', 'media': 0.0, 'optativo': True},  # Optional with 0
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
        
        # Optional with grade should count - student should be REPROVADO
        assert resultado['resultado'] == 'REPROVADO', \
            f"Optional with 0.0 grade should count, got {resultado['resultado']}"
        assert 'Inglês' in resultado['componentes_reprovados'], \
            "Inglês should be in failed components"
        print(f"✅ Test passed: Optional with 0.0 → counts as failed")
    
    def test_optional_component_without_grade_ignored(self):
        """Optional component without grade (None) should be ignored"""
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 7.0, 'optativo': False},
            {'nome': 'Português', 'media': 7.0, 'optativo': False},
            {'nome': 'Inglês', 'media': None, 'optativo': True},  # Optional without grade
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
        
        # Optional without grade should be ignored - student should be APROVADO
        assert resultado['resultado'] == 'APROVADO', \
            f"Optional without grade should be ignored, got {resultado['resultado']}"
        print(f"✅ Test passed: Optional without grade → ignored, APROVADO")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
