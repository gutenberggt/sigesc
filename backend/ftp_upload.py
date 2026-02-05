"""
Módulo de upload de arquivos via FTP para servidor externo
"""
import ftplib
import os
from pathlib import Path
from typing import Optional, Tuple
import uuid
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv(override=True)

def get_ftp_config():
    """Retorna configuração FTP lida das variáveis de ambiente"""
    return {
        "host": os.environ.get("FTP_HOST", ""),
        "port": int(os.environ.get("FTP_PORT", "21")),
        "user": os.environ.get("FTP_USER", ""),
        "password": os.environ.get("FTP_PASSWORD", ""),
        "base_path": os.environ.get("FTP_BASE_PATH", "/public_html/imagens"),
        "base_url": os.environ.get("FTP_BASE_URL", "https://aprenderdigital.top/imagens")
    }

# Mapeamento de tipo de arquivo para pasta
FILE_TYPE_FOLDERS = {
    "profile": "user",      # Fotos de perfil de usuários
    "avatar": "user",       # Avatares
    "student": "user",      # Fotos de alunos
    "staff": "user",        # Fotos de servidores
    "cover": "capa",        # Fotos de capa
    "document": "doc",      # Documentos (PDFs, etc.)
    "laudo": "doc",         # Laudos médicos
    "logotipo": "logotipo", # Logotipos (mantenedora, escolas)
    "brasao": "brasao",     # Brasões
    "default": "user"       # Padrão
}

def get_folder_for_file(filename: str, file_type: str = "default") -> str:
    """
    Determina a pasta de destino baseado no tipo de arquivo
    """
    # Verifica pela extensão se é documento
    ext = Path(filename).suffix.lower()
    if ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']:
        return FILE_TYPE_FOLDERS["document"]
    
    # Usa o tipo fornecido
    return FILE_TYPE_FOLDERS.get(file_type, FILE_TYPE_FOLDERS["default"])


def upload_to_ftp(
    file_content: bytes, 
    original_filename: str, 
    file_type: str = "default"
) -> Tuple[bool, str, Optional[str]]:
    """
    Faz upload de um arquivo para o servidor FTP
    
    Args:
        file_content: Conteúdo do arquivo em bytes
        original_filename: Nome original do arquivo
        file_type: Tipo do arquivo (profile, cover, document, etc.)
    
    Returns:
        Tuple[success, url_or_error, filename]
    """
    # Obtém configuração FTP atualizada
    FTP_CONFIG = get_ftp_config()
    
    # Verifica se FTP está configurado
    if not FTP_CONFIG["host"] or not FTP_CONFIG["user"]:
        return False, "FTP não configurado (FTP_HOST ou FTP_USER ausente)", None
    
    ftp = None
    try:
        # Gera nome único para o arquivo
        ext = Path(original_filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{ext}"
        
        # Determina a pasta de destino
        folder = get_folder_for_file(original_filename, file_type)
        
        # Conecta ao FTP
        ftp = ftplib.FTP()
        ftp.connect(FTP_CONFIG["host"], FTP_CONFIG["port"], timeout=30)
        ftp.login(FTP_CONFIG["user"], FTP_CONFIG["password"])
        
        # Navega para a pasta de destino
        target_path = f"{FTP_CONFIG['base_path']}/{folder}"
        ftp.cwd(target_path)
        
        # Salva temporariamente o arquivo
        temp_path = f"/tmp/{unique_filename}"
        with open(temp_path, 'wb') as f:
            f.write(file_content)
        
        # Faz upload em modo binário
        with open(temp_path, 'rb') as f:
            ftp.storbinary(f'STOR {unique_filename}', f)
        
        # Remove arquivo temporário
        os.remove(temp_path)
        
        # Fecha conexão
        ftp.quit()
        
        # Retorna URL pública do arquivo
        public_url = f"{FTP_CONFIG['base_url']}/{folder}/{unique_filename}"
        
        return True, public_url, unique_filename
        
    except ftplib.all_errors as e:
        error_msg = f"Erro FTP: {str(e)}"
        print(error_msg)
        return False, error_msg, None
        
    except Exception as e:
        error_msg = f"Erro ao fazer upload: {str(e)}"
        print(error_msg)
        return False, error_msg, None
        
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass


def delete_from_ftp(file_url: str) -> Tuple[bool, str]:
    """
    Remove um arquivo do servidor FTP
    
    Args:
        file_url: URL pública do arquivo
    
    Returns:
        Tuple[success, message]
    """
    # Obtém configuração FTP atualizada
    FTP_CONFIG = get_ftp_config()
    
    ftp = None
    try:
        # Extrai o caminho do arquivo da URL
        if not file_url.startswith(FTP_CONFIG["base_url"]):
            return False, "URL não corresponde ao servidor configurado"
        
        relative_path = file_url.replace(FTP_CONFIG["base_url"], "")
        # relative_path será algo como "/user/abc123.jpg"
        
        # Conecta ao FTP
        ftp = ftplib.FTP()
        ftp.connect(FTP_CONFIG["host"], FTP_CONFIG["port"], timeout=30)
        ftp.login(FTP_CONFIG["user"], FTP_CONFIG["password"])
        
        # Navega para a pasta base
        ftp.cwd(FTP_CONFIG["base_path"])
        
        # Remove o arquivo (remove a barra inicial)
        ftp.delete(relative_path.lstrip('/'))
        
        ftp.quit()
        
        return True, "Arquivo removido com sucesso"
        
    except ftplib.error_perm as e:
        if "550" in str(e):
            return False, "Arquivo não encontrado"
        return False, f"Erro de permissão: {str(e)}"
        
    except Exception as e:
        return False, f"Erro ao remover arquivo: {str(e)}"
        
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass


# Teste do módulo
if __name__ == "__main__":
    print("Testando conexão FTP...")
    
    # Teste simples de upload
    test_content = b"Teste de upload FTP"
    success, result, filename = upload_to_ftp(test_content, "teste.txt", "document")
    
    if success:
        print(f"✅ Upload bem sucedido!")
        print(f"   URL: {result}")
        
        # Teste de remoção
        del_success, del_msg = delete_from_ftp(result)
        print(f"   Remoção: {del_msg}")
    else:
        print(f"❌ Falha: {result}")
