from app.db.session import SessionLocal
from app.db.models import ConversionJob
from sqlalchemy.orm import joinedload
import json
import json
from pathlib import Path

def debug_latest_job():
    db = SessionLocal()
    try:
        job = db.query(ConversionJob).order_by(ConversionJob.created_at.desc()).first()
        if not job:
            print("No jobs found.")
            return

        print(f"Job ID: {job.id}")
        print(f"Status: {job.status}")
        print(f"Mapping Profile ID: {job.mapping_profile_id}")
        print(f"Parsing Config: {job.parsing_config}")
        
        # Check Mapping Profile
        if job.mapping_profile_id:
            from app.db.models import MappingProfile
            profile = db.query(MappingProfile).options(joinedload(MappingProfile.mappings)).filter(MappingProfile.id == job.mapping_profile_id).first()
            if profile:
                print(f"Mapping Profile: {profile.name}")
                print(f"Mappings: {[f'{m.source_code} -> {m.target_status}' for m in profile.mappings]}")
            else:
                print("Mapping profile not found in DB.")

        # Check Raw Data
        if job.raw_data_path:
            path = Path(job.raw_data_path)
            if path.exists():
                with open(path, 'r') as f:
                    data = json.load(f)
                    print(f"Raw Data Record Count: {len(data)}")
                    if len(data) > 0:
                        print("Sample Raw Record (First 2):")
                        print(json.dumps(data[:2], indent=2))
            else:
                print(f"Raw file not found at {path}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    debug_latest_job()
