import bcrypt as _bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import os
import secrets
import uuid
import logging

logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente do .env
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configurações JWT - SECRET_KEY obrigatória em produção
SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is required")
ALGORITHM = 'HS256'

# PATCH 3.1: Configurações de expiração com valores seguros
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINUTES', 15))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get('REFRESH_TOKEN_EXPIRE_DAYS', 7))

# G2 (Fev/2026): HttpOnly cookies config
# COOKIE_SECURE=true em produção (HTTPS). No preview emergentagent.com é HTTPS, OK.
# SAMESITE=lax é o padrão recomendado para sessões web tradicionais.
# Domínio inherido do request (host-only) — multi-tenant funciona naturalmente
# pois cada domínio do tenant recebe seus próprios cookies.
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true'
COOKIE_SAMESITE = os.environ.get('COOKIE_SAMESITE', 'lax')

ACCESS_COOKIE_NAME = 'sigesc_access'
REFRESH_COOKIE_NAME = 'sigesc_refresh'
CSRF_COOKIE_NAME = 'sigesc_csrf'
CSRF_HEADER_NAME = 'X-CSRF-Token'


def _access_cookie_kwargs() -> Dict[str, Any]:
    return {
        'httponly': True,
        'secure': COOKIE_SECURE,
        'samesite': COOKIE_SAMESITE,
        'max_age': ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        'path': '/',
    }


def _refresh_cookie_kwargs() -> Dict[str, Any]:
    return {
        'httponly': True,
        'secure': COOKIE_SECURE,
        'samesite': COOKIE_SAMESITE,
        'max_age': REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        # Escopa o refresh_token apenas às rotas de auth que o usam.
        # Minimiza superfície de ataque: não é enviado em toda requisição.
        'path': '/api/auth',
    }


def _csrf_cookie_kwargs() -> Dict[str, Any]:
    # CSRF cookie é lido por JS (double-submit) → httponly=False.
    # Secure e SameSite continuam valendo.
    return {
        'httponly': False,
        'secure': COOKIE_SECURE,
        'samesite': COOKIE_SAMESITE,
        'max_age': ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        'path': '/',
    }


def generate_csrf_token() -> str:
    """Gera um token CSRF criptograficamente forte (32 bytes = 43 chars url-safe)."""
    return secrets.token_urlsafe(32)


def set_auth_cookies(response, *, access_token: str, refresh_token: str, csrf_token: str) -> None:
    """Seta os 3 cookies de autenticação na resposta HTTP.

    access_token: HttpOnly, 15min, path=/
    refresh_token: HttpOnly, 7d, path=/api/auth (minimiza exposição)
    csrf_token: NOT HttpOnly, 15min, path=/ (JS lê e envia via X-CSRF-Token)
    """
    response.set_cookie(ACCESS_COOKIE_NAME, access_token, **_access_cookie_kwargs())
    response.set_cookie(REFRESH_COOKIE_NAME, refresh_token, **_refresh_cookie_kwargs())
    response.set_cookie(CSRF_COOKIE_NAME, csrf_token, **_csrf_cookie_kwargs())


def clear_auth_cookies(response) -> None:
    """Remove os 3 cookies de auth (logout)."""
    response.delete_cookie(ACCESS_COOKIE_NAME, path='/')
    response.delete_cookie(REFRESH_COOKIE_NAME, path='/api/auth')
    response.delete_cookie(CSRF_COOKIE_NAME, path='/')


def hash_password(password: str) -> str:
    """Gera hash da senha usando bcrypt diretamente"""
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha corresponde ao hash usando bcrypt diretamente"""
    try:
        return _bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Cria token de acesso JWT - PATCH 3.1: TTL reduzido + iat para suportar revogação via revoke_all"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # iat (numérico) permite que TokenBlacklistService.is_token_revoked compare
    # com revoke_all_before quando logout invalida todas as sessões do usuário.
    to_encode.update({
        'exp': expire,
        'type': 'access',
        'iat': int(datetime.now(timezone.utc).timestamp())
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Cria token de refresh JWT
    PATCH 3.2: Adiciona jti (JWT ID) único para suportar rotação e revogação
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # PATCH 3.2: jti único para cada token (permite revogação individual)
    token_id = str(uuid.uuid4())
    
    to_encode.update({
        'exp': expire, 
        'type': 'refresh',
        'jti': token_id,  # PATCH 3.2: ID único do token
        'iat': int(datetime.now(timezone.utc).timestamp())  # Timestamp de criação (numérico)
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodifica e valida token JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ============= PATCH 3.3: TOKEN BLACKLIST SERVICE =============

class TokenBlacklistService:
    """
    Serviço para gerenciar blacklist de tokens revogados.
    PATCH 3.3: Permite revogar tokens específicos ou todos de um usuário.
    """
    
    def __init__(self):
        self.db = None
        self._collection_name = 'token_blacklist'
    
    def set_db(self, db):
        """Configura a conexão com o banco de dados"""
        self.db = db
    
    async def ensure_index(self):
        """Cria índices necessários para performance"""
        if self.db is None:
            return
        
        try:
            # Índice para busca rápida por jti
            await self.db[self._collection_name].create_index('jti', unique=True, sparse=True)
            # Índice para busca por user_id
            await self.db[self._collection_name].create_index('user_id')
            # TTL index para limpeza automática de tokens expirados
            await self.db[self._collection_name].create_index(
                'expires_at', 
                expireAfterSeconds=0  # Remove automaticamente quando expires_at é atingido
            )
            logger.info("[TokenBlacklist] Índices criados/verificados")
        except Exception as e:
            logger.error(f"[TokenBlacklist] Erro ao criar índices: {e}")
    
    async def revoke_token(self, jti: str, user_id: str, expires_at: datetime, reason: str = None):
        """
        Adiciona um token específico à blacklist.
        O token será automaticamente removido após expirar (TTL index).
        """
        if self.db is None:
            logger.warning("[TokenBlacklist] DB não configurado, token não revogado")
            return False
        
        try:
            await self.db[self._collection_name].insert_one({
                'jti': jti,
                'user_id': user_id,
                'revoked_at': datetime.now(timezone.utc),
                'expires_at': expires_at,
                'reason': reason or 'manual_revocation'
            })
            logger.info(f"[TokenBlacklist] Token revogado: jti={jti[:8]}... user={user_id}")
            return True
        except Exception as e:
            # Ignora erro de duplicata (token já revogado)
            if 'duplicate key' in str(e).lower():
                return True
            logger.error(f"[TokenBlacklist] Erro ao revogar token: {e}")
            return False
    
    async def revoke_all_user_tokens(self, user_id: str, reason: str = None):
        """
        Revoga todos os tokens de um usuário (logout de todas as sessões).
        Usado quando o usuário muda a senha ou solicita logout global.
        """
        if self.db is None:
            return False
        
        try:
            # Resolve race condition de precisão entre JWT iat (segundos inteiros)
            # e revoke_all_before (datetime com microssegundos).
            # Estratégia: gravamos revoke_before no FINAL do segundo (microsecond=999999).
            # Resultado: tokens com iat == segundo_atual são revogados; tokens emitidos
            # a partir do próximo segundo (iat = segundo_atual + 1) sobrevivem.
            # Trade-off aceito: para re-login imediatamente após revoke, o user precisa
            # aguardar até a virada do segundo (≤ 1s). Em produção isso é trivial pois
            # o fluxo passa pela UI (tela de login + digitação > 1s).
            now = datetime.now(timezone.utc)
            revoke_before = now.replace(microsecond=999999)
            await self.db[self._collection_name].insert_one({
                'user_id': user_id,
                'revoke_all_before': revoke_before,
                'revoked_at': now,
                'expires_at': now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS + 1),
                'reason': reason or 'revoke_all_sessions'
            })
            logger.info(f"[TokenBlacklist] Todos os tokens revogados para user={user_id}")
            return True
        except Exception as e:
            logger.error(f"[TokenBlacklist] Erro ao revogar todos tokens: {e}")
            return False
    
    async def is_token_revoked(self, jti: str = None, user_id: str = None, issued_at = None) -> bool:
        """
        Verifica se um token foi revogado.
        Retorna True se o token está na blacklist ou se foi emitido antes de um revoke_all.
        issued_at pode ser string ISO, timestamp numérico ou datetime.
        """
        if self.db is None:
            return False  # Se não há DB, assume que não está revogado
        
        try:
            # Verifica revogação específica por jti
            if jti:
                revoked = await self.db[self._collection_name].find_one({'jti': jti})
                if revoked:
                    return True
            
            # Verifica se há revoke_all para este usuário
            if user_id and issued_at:
                try:
                    # Converte issued_at para datetime
                    if isinstance(issued_at, str):
                        token_issued = datetime.fromisoformat(issued_at.replace('Z', '+00:00'))
                    elif isinstance(issued_at, (int, float)):
                        # Timestamp numérico
                        token_issued = datetime.fromtimestamp(issued_at, tz=timezone.utc)
                    else:
                        token_issued = issued_at
                    
                    revoke_all = await self.db[self._collection_name].find_one({
                        'user_id': user_id,
                        'revoke_all_before': {'$exists': True}
                    }, sort=[('revoke_all_before', -1)])
                    
                    if revoke_all:
                        # Motor sem tz_aware retorna datetime naive do Mongo;
                        # nosso token_issued é aware. Normalizamos para evitar
                        # TypeError na comparação que era engolido pelo except.
                        revoke_before = revoke_all['revoke_all_before']
                        if revoke_before.tzinfo is None:
                            revoke_before = revoke_before.replace(tzinfo=timezone.utc)
                        if token_issued < revoke_before:
                            return True
                except Exception as e:
                    logger.debug(f"[TokenBlacklist] Erro ao verificar revoke_all: {e}")
            
            return False
        except Exception as e:
            logger.error(f"[TokenBlacklist] Erro ao verificar blacklist: {e}")
            return False  # Em caso de erro, permite o token (fail-open)
    
    async def cleanup_expired(self):
        """Remove manualmente tokens expirados (backup do TTL index)"""
        if self.db is None:
            return 0
        
        try:
            result = await self.db[self._collection_name].delete_many({
                'expires_at': {'$lt': datetime.now(timezone.utc)}
            })
            if result.deleted_count > 0:
                logger.info(f"[TokenBlacklist] Removidos {result.deleted_count} tokens expirados")
            return result.deleted_count
        except Exception as e:
            logger.error(f"[TokenBlacklist] Erro ao limpar tokens: {e}")
            return 0


# Instância singleton do serviço
token_blacklist = TokenBlacklistService()

def get_school_ids_from_links(school_links: list) -> list:
    """Extrai IDs de escolas dos vínculos"""
    return [link['school_id'] for link in school_links]
