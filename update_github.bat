@echo off
REM Este script atualiza suas alterações para o GitHub.

echo.
echo === Verificando o status do Git ===
git status

echo.
echo === Adicionando todas as alteracoes ===
git add .
IF %ERRORLEVEL% NEQ 0 (
    echo Erro ao adicionar arquivos. Abortando.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo === Solicitando a mensagem do commit ===
set /p commitMessage="Digite a mensagem do commit: "

echo.
echo === Criando o commit local ===
git commit -m "%commitMessage%"
IF %ERRORLEVEL% NEQ 0 (
    echo Erro ao criar o commit. Verifique suas alteracoes ou mensagem. Abortando.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo === Enviando as alteracoes para o GitHub (branch main) ===
git push origin main
IF %ERRORLEVEL% NEQ 0 (
    echo Erro ao enviar para o GitHub. Verifique sua conexao ou permissoes.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo === Atualizacao para o GitHub concluida com sucesso! ===
pause