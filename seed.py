"""Script para popular o banco com dados iniciais (disciplinas e admin)."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import SessionLocal, engine, Base
from app.core.security import hash_password
from app.models.models import Disciplina, Usuario, RoleEnum

# Criar tabelas
Base.metadata.create_all(bind=engine)


DISCIPLINAS = [
    "Tubulação",
    "Instrumentação",
    "Elétrica",
    "Equipamento Estático",
    "Equipamento Dinâmico",
    "Civil",
    "Telecom",
    "Estrutura Metálica",
    "TAP",
    "Segurança",
]


def seed():
    db = SessionLocal()
    try:
        # Criar disciplinas
        for nome in DISCIPLINAS:
            existing = db.query(Disciplina).filter(Disciplina.nome == nome).first()
            if not existing:
                db.add(Disciplina(nome=nome))
                print(f"  ✓ Disciplina criada: {nome}")
            else:
                print(f"  - Disciplina já existe: {nome}")

        # Criar usuário administrador padrão
        admin_email = "admin@commissioning.com"
        existing_admin = db.query(Usuario).filter(Usuario.email == admin_email).first()
        if not existing_admin:
            admin = Usuario(
                nome="Administrador",
                email=admin_email,
                senha_hash=hash_password("admin123"),
                role=RoleEnum.ADMINISTRADOR,
                ativo=True,
            )
            db.add(admin)
            print(f"  ✓ Usuário admin criado: {admin_email} (senha: admin123)")
        else:
            print(f"  - Admin já existe: {admin_email}")

        db.commit()
        print("\n✅ Seed concluído com sucesso!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Erro no seed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
