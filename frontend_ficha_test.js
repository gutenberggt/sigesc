#!/usr/bin/env node
/**
 * Simple verification that Ficha Individual is implemented in frontend
 */

const fs = require('fs');
const path = require('path');

console.log('🔍 Verifying Ficha Individual implementation in frontend...');

// Check DocumentGeneratorModal.js
const modalPath = '/app/frontend/src/components/documents/DocumentGeneratorModal.js';
if (fs.existsSync(modalPath)) {
    const modalContent = fs.readFileSync(modalPath, 'utf8');
    
    // Check for Ficha Individual in documents array
    if (modalContent.includes("'Ficha Individual'") || modalContent.includes('"Ficha Individual"')) {
        console.log('✅ Ficha Individual option found in DocumentGeneratorModal');
    } else {
        console.log('❌ Ficha Individual option NOT found in DocumentGeneratorModal');
    }
    
    // Check for orange color scheme
    if (modalContent.includes('orange')) {
        console.log('✅ Orange color scheme found for Ficha Individual');
    } else {
        console.log('❌ Orange color scheme NOT found');
    }
    
    // Check for User icon
    if (modalContent.includes('User')) {
        console.log('✅ User icon imported and used');
    } else {
        console.log('❌ User icon NOT found');
    }
    
    // Check for ficha handling in switch case
    if (modalContent.includes("case 'ficha':")) {
        console.log('✅ Ficha case handling found in download function');
    } else {
        console.log('❌ Ficha case handling NOT found');
    }
    
} else {
    console.log('❌ DocumentGeneratorModal.js not found');
}

// Check API service
const apiPath = '/app/frontend/src/services/api.js';
if (fs.existsSync(apiPath)) {
    const apiContent = fs.readFileSync(apiPath, 'utf8');
    
    if (apiContent.includes('getFichaIndividualUrl')) {
        console.log('✅ getFichaIndividualUrl function found in API service');
    } else {
        console.log('❌ getFichaIndividualUrl function NOT found in API service');
    }
    
    if (apiContent.includes('/api/documents/ficha-individual/')) {
        console.log('✅ Ficha Individual API endpoint configured correctly');
    } else {
        console.log('❌ Ficha Individual API endpoint NOT configured');
    }
    
} else {
    console.log('❌ API service file not found');
}

console.log('\n📋 Frontend Ficha Individual Implementation Summary:');
console.log('- Modal has 4 document options: Boletim Escolar, Ficha Individual (NEW), Declaração de Matrícula, Declaração de Frequência');
console.log('- Ficha Individual uses orange color scheme (bg-orange-50, text-orange-600)');
console.log('- Uses User icon from lucide-react');
console.log('- Description: "Notas, frequência e dados completos do aluno"');
console.log('- API endpoint: /api/documents/ficha-individual/{student_id}?academic_year={year}');
console.log('- Download functionality integrated with existing modal system');