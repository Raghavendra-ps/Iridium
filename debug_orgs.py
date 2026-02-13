from sqlalchemy import create_engine, text
from app.core.config import settings

try:
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    with engine.connect() as conn:
        print("\n--- ORGANIZATIONS ---")
        result = conn.execute(text("SELECT id, name, source FROM organizations ORDER BY id DESC LIMIT 5"))
        print(f"{'ID':<5} {'NAME':<30} {'SOURCE':<15}")
        print("-" * 50)
        for row in result:
            print(f"{row.id:<5} {row.name:<30} {row.source:<15}")

        print("\n--- LINKED ORGANIZATIONS ---")
        result = conn.execute(text("SELECT id, organization_id, erpnext_url FROM linked_organizations ORDER BY id DESC LIMIT 5"))
        print(f"{'ID':<5} {'ORG_ID':<10} {'URL':<30}")
        print("-" * 50)
        for row in result:
            print(f"{row.id:<5} {row.organization_id:<10} {row.erpnext_url:<30}")
except Exception as e:
    print(f"Error: {e}")
