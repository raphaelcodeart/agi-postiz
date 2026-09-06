import argparse
import sys
from app.db.session import SessionLocal
from app.core.security import SecurityService
from app.models.administrator import Administrator

def create_admin(email: str, password: str, name: str):
    db = SessionLocal()
    try:
        # Check if email exists
        existing = db.query(Administrator).filter(Administrator.email == email).first()
        if existing:
            print(f"Error: An administrator with email '{email}' already exists.")
            sys.exit(1)

        admin = Administrator(
            email=email,
            password_hash=SecurityService.hash_password(password),
            full_name=name,
            is_active=True
        )
        db.add(admin)
        db.commit()
        print(f"Success: Created administrator '{name}' ({email}) successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error creating administrator: {str(e)}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new system administrator.")
    parser.add_argument("--email", required=True, help="Email address of the administrator.")
    parser.add_argument("--password", required=True, help="Password of the administrator.")
    parser.add_argument("--name", required=True, help="Full name of the administrator.")
    
    args = parser.parse_args()
    create_admin(args.email, args.password, args.name)
