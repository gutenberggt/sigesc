#!/usr/bin/env python3
import asyncio
import os
from playwright.async_api import async_playwright

BASE_URL = "https://aee-diary-dev.preview.emergentagent.com"
OUTPUT_DIR = "/app/frontend/public/tutorials"

async def main():
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 900})
        
        # Screenshot 1: Tela de Login vazia
        print("Capturando tela-login.png...")
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{OUTPUT_DIR}/tela-login.png")
        print("OK: tela-login.png")
        
        # Screenshot 2: Tela de Login preenchida
        print("Capturando tela-login-preenchido.png...")
        await page.fill('input[type="email"]', 'teste@sigesc.com')
        await page.fill('input[type="password"]', 'teste')
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{OUTPUT_DIR}/tela-login-preenchido.png")
        print("OK: tela-login-preenchido.png")
        
        # Login
        print("Fazendo login...")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)
        await page.wait_for_load_state('networkidle')
        
        # Screenshot 3: Dashboard
        print("Capturando tela-dashboard.png...")
        await page.screenshot(path=f"{OUTPUT_DIR}/tela-dashboard.png")
        print("OK: tela-dashboard.png")
        
        # Screenshot 4: Tela de Perfil
        print("Capturando tela-perfil.png...")
        await page.click('text=Meu Perfil')
        await page.wait_for_timeout(2000)
        await page.wait_for_load_state('networkidle')
        await page.screenshot(path=f"{OUTPUT_DIR}/tela-perfil.png")
        print("OK: tela-perfil.png")
        
        # Screenshot 5: Tela de Alunos
        print("Capturando tela-alunos.png...")
        await page.goto(f"{BASE_URL}/admin/students")
        await page.wait_for_timeout(3000)
        await page.wait_for_load_state('networkidle')
        await page.screenshot(path=f"{OUTPUT_DIR}/tela-alunos.png")
        print("OK: tela-alunos.png")
        
        await browser.close()
        
    print("\n✅ Todos os screenshots foram capturados com sucesso!")
    print(f"Arquivos salvos em: {OUTPUT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
