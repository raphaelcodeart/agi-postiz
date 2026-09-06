from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from app.core.config import settings

# Audiences a JWT can be issued for. Kept as plain constants rather than an enum
# so they can be compared against a raw claim without conversion.
TOKEN_TYPE_ADMIN = "admin"
TOKEN_TYPE_PORTAL_USER = "portal_user"

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
    def create_access_token(
        subject: Union[str, Any],
        expires_delta: Optional[timedelta] = None,
        token_type: str = TOKEN_TYPE_ADMIN,
    ) -> str:
        """
        Issue a JWT bound to one audience.

        ``token_type`` is what keeps the two audiences apart. Both an
        administrator and a portal user are identified by a UUID in ``sub``, so
        without this claim the only thing preventing a user token from being
        accepted on an admin endpoint would be that the lookup happens to query
        a different table. That is an accident, not a control: any future
        endpoint that resolves a subject more loosely would turn it into
        privilege escalation. The claim makes the separation explicit and
        checkable at the edge.
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = {"exp": expire, "sub": str(subject), "typ": token_type}
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
        return encoded_jwt

    @staticmethod
    def verify_access_token(token: str, expected_type: str = TOKEN_TYPE_ADMIN) -> Optional[str]:
        """
        Return the subject only if the token was issued for this audience.

        Tokens minted before ``typ`` existed carry no claim; they are treated as
        admin tokens, which is what they were, so existing sessions survive the
        change. Portal tokens always carry the claim and are therefore never
        accepted where an admin token is expected.
        """
        try:
            decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except JWTError:
            return None

        if decoded_token.get("typ", TOKEN_TYPE_ADMIN) != expected_type:
            return None

        return decoded_token.get("sub")


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
