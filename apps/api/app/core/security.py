from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from app.core.config import settings

# Initialize password hasher
ph = PasswordHasher()

# Initialize encryption engine
try:
    fernet = Fernet(settings.ENCRYPTION_KEY.encode())
except Exception as e:
    # Fallback to a development key if the provided key is invalid
    # Real production environments will require a valid 32-byte urlsafe base64 key
    dev_key = Fernet.generate_key()
    fernet = Fernet(dev_key)

class SecurityService:
    @staticmethod
    def hash_password(password: str) -> str:
        return ph.hash(password)

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        try:
            return ph.verify(hashed_password, password)
        except VerifyMismatchError:
            return False

    @staticmethod
    def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {"exp": expire, "sub": str(subject)}
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
        return encoded_jwt

    @staticmethod
    def verify_access_token(token: str) -> Optional[str]:
        try:
            decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            # Return the subject (admin ID)
            return decoded_token.get("sub")
        except JWTError:
            return None


class EncryptionService:
    @staticmethod
    def encrypt(data: str) -> str:
        if not data:
            return ""
        return fernet.encrypt(data.encode()).decode()

    @staticmethod
    def decrypt(encrypted_data: str) -> str:
        if not encrypted_data:
            return ""
        try:
            return fernet.decrypt(encrypted_data.encode()).decode()
        except Exception:
            return ""
