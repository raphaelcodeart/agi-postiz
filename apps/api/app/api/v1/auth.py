from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.config import settings
from app.core.security import SecurityService
from app.models.administrator import Administrator
from app.schemas.schemas import LoginRequest, TokenResponse, AdminResponse

router = APIRouter()

# Setup OAuth2PasswordBearer flow for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def get_current_admin(
    db: Session = Depends(get_db), 
    token: str = Depends(oauth2_scheme)
) -> Administrator:
    """Dependency to retrieve and validate JWT token session."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    admin_id_str = SecurityService.verify_access_token(token)
    if not admin_id_str:
        raise credentials_exception
        
    admin = db.query(Administrator).filter(Administrator.id == admin_id_str).first()
    if not admin:
        raise credentials_exception
        
    if not admin.is_active:
        raise HTTPException(status_code=400, detail="Inactive administrator account")
        
    return admin


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate administrator credentials and return access JWT."""
    admin = db.query(Administrator).filter(Administrator.email == request.email).first()
    if not admin or not SecurityService.verify_password(request.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not admin.is_active:
        raise HTTPException(status_code=400, detail="Administrator account is inactive")
        
    # Update last login time
    from datetime import datetime, timezone
    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()

    access_token = SecurityService.create_access_token(subject=admin.id)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=AdminResponse)
def get_me(current_admin: Administrator = Depends(get_current_admin)):
    """Retrieve details of the currently authenticated administrator."""
    return current_admin
