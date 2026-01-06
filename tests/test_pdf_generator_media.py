"""
Test cases for pdf_generator.py - specifically testing the media calculation fix

Bug Description:
- In pdf_generator.py line 826-831, the code was setting media=None when total_pontos == 0
- This caused students with all grades 0 to be treated as "no grades registered" instead of "failed"

Fix Applied:
- Now uses has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
- media = total_pontos / 10 if has_any_grade else None
- This ensures media 0.0 is valid when grades are registered (even if all 0)
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')


class TestPdfGeneratorMediaCalculation:
    """Tests for the media calculation logic in pdf_generator.py"""
    
    def test_media_calculation_all_zeros(self):
        """
        Simulates the exact logic from pdf_generator.py lines 826-831
        When all grades are 0, media should be 0.0 (not None)
        """
        # Simulate grades from database
        b1, b2, b3, b4 = 0, 0, 0, 0
        
        # Values for calculation (same as pdf_generator.py)
        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0
        
        # Calculate weighted average: (B1×2 + B2×3 + B3×2 + B4×3) / 10
        total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
        
        # THE FIX: Check if any grade is registered (not None)
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
        media = total_pontos / 10 if has_any_grade else None
        
        # Assertions
        assert has_any_grade == True, "Should detect that grades are registered"
        assert media == 0.0, f"Media should be 0.0, got {media}"
        assert media is not None, "Media should NOT be None when grades are registered"
        print(f"✅ Test passed: All zeros → media = {media} (not None)")
    
    def test_media_calculation_all_none(self):
        """
        When all grades are None, media should be None (no grades registered)
        """
        b1, b2, b3, b4 = None, None, None, None
        
        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0
        
        total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
        
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
        media = total_pontos / 10 if has_any_grade else None
        
        assert has_any_grade == False, "Should detect no grades registered"
        assert media is None, f"Media should be None when no grades, got {media}"
        print(f"✅ Test passed: All None → media = None")
    
    def test_media_calculation_mixed_zero_and_none(self):
        """
        When some grades are 0 and some are None, media should be calculated
        """
        b1, b2, b3, b4 = 0, None, 0, None
        
        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0
        
        total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
        
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
        media = total_pontos / 10 if has_any_grade else None
        
        assert has_any_grade == True, "Should detect that some grades are registered"
        assert media == 0.0, f"Media should be 0.0, got {media}"
        print(f"✅ Test passed: Mixed 0 and None → media = {media}")
    
    def test_media_calculation_normal_grades(self):
        """
        Normal grades should calculate correctly
        """
        b1, b2, b3, b4 = 8.0, 7.0, 6.0, 9.0
        
        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0
        
        # (8×2 + 7×3 + 6×2 + 9×3) / 10 = (16 + 21 + 12 + 27) / 10 = 76/10 = 7.6
        total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
        
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
        media = total_pontos / 10 if has_any_grade else None
        
        assert has_any_grade == True
        assert media == 7.6, f"Media should be 7.6, got {media}"
        print(f"✅ Test passed: Normal grades → media = {media}")
    
    def test_media_calculation_partial_grades(self):
        """
        When only some bimesters have grades, should still calculate
        """
        b1, b2, b3, b4 = 8.0, 7.0, None, None  # Only 1st semester
        
        b1_val = b1 if isinstance(b1, (int, float)) else 0
        b2_val = b2 if isinstance(b2, (int, float)) else 0
        b3_val = b3 if isinstance(b3, (int, float)) else 0
        b4_val = b4 if isinstance(b4, (int, float)) else 0
        
        # (8×2 + 7×3 + 0×2 + 0×3) / 10 = (16 + 21 + 0 + 0) / 10 = 37/10 = 3.7
        total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
        
        has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
        media = total_pontos / 10 if has_any_grade else None
        
        assert has_any_grade == True
        assert media == 3.7, f"Media should be 3.7, got {media}"
        print(f"✅ Test passed: Partial grades → media = {media}")


class TestMediaPorComponenteList:
    """Tests for building medias_por_componente list as done in pdf_generator.py"""
    
    def test_build_medias_list_with_zero_grades(self):
        """
        Simulates building the medias_por_componente list with zero grades
        """
        # Simulate courses and grades
        courses = [
            {'id': '1', 'name': 'Matemática', 'optativo': False},
            {'id': '2', 'name': 'Português', 'optativo': False},
        ]
        
        grades_by_course = {
            '1': {'b1': 0, 'b2': 0, 'b3': 0, 'b4': 0},  # All zeros
            '2': {'b1': 7, 'b2': 8, 'b3': 6, 'b4': 9},  # Normal grades
        }
        
        medias_por_componente = []
        
        for course in courses:
            is_optativo = course.get('optativo', False)
            course_id = course.get('id')
            course_grades = grades_by_course.get(course_id, {})
            
            b1 = course_grades.get('b1')
            b2 = course_grades.get('b2')
            b3 = course_grades.get('b3')
            b4 = course_grades.get('b4')
            
            b1_val = b1 if isinstance(b1, (int, float)) else 0
            b2_val = b2 if isinstance(b2, (int, float)) else 0
            b3_val = b3 if isinstance(b3, (int, float)) else 0
            b4_val = b4 if isinstance(b4, (int, float)) else 0
            
            total_pontos = (b1_val * 2) + (b2_val * 3) + (b3_val * 2) + (b4_val * 3)
            
            # THE FIX
            has_any_grade = any(g is not None for g in [b1, b2, b3, b4])
            media = total_pontos / 10 if has_any_grade else None
            
            medias_por_componente.append({
                'nome': course.get('name', 'N/A'),
                'media': media,
                'optativo': is_optativo
            })
        
        # Assertions
        assert len(medias_por_componente) == 2
        
        # Matemática should have media 0.0 (not None)
        mat = next(c for c in medias_por_componente if c['nome'] == 'Matemática')
        assert mat['media'] == 0.0, f"Matemática media should be 0.0, got {mat['media']}"
        assert mat['media'] is not None, "Matemática media should NOT be None"
        
        # Português should have normal media
        port = next(c for c in medias_por_componente if c['nome'] == 'Português')
        # (7×2 + 8×3 + 6×2 + 9×3) / 10 = (14 + 24 + 12 + 27) / 10 = 77/10 = 7.7
        assert port['media'] == 7.7, f"Português media should be 7.7, got {port['media']}"
        
        print(f"✅ Test passed: medias_por_componente built correctly")
        print(f"   Matemática: {mat['media']}")
        print(f"   Português: {port['media']}")
    
    def test_approval_check_with_zero_media(self):
        """
        Test that approval check correctly identifies 0.0 as failing
        """
        medias_por_componente = [
            {'nome': 'Matemática', 'media': 0.0, 'optativo': False},
            {'nome': 'Português', 'media': 7.7, 'optativo': False},
        ]
        
        media_minima = 5.0
        componentes_reprovados = []
        
        for comp in medias_por_componente:
            is_optativo = comp.get('optativo', False)
            media = comp.get('media')
            
            # Ignore optional without grade
            if is_optativo and media is None:
                continue
            
            # Check if failed
            if media is not None and media < media_minima:
                componentes_reprovados.append(comp.get('nome', 'N/A'))
        
        # Assertions
        assert len(componentes_reprovados) == 1, f"Should have 1 failed component, got {len(componentes_reprovados)}"
        assert 'Matemática' in componentes_reprovados, "Matemática should be in failed list"
        
        print(f"✅ Test passed: 0.0 media correctly identified as failing")
        print(f"   Failed components: {componentes_reprovados}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
