import json
import pandas as pd
from app.db.session import SessionLocal
from app.db.models import ConversionJob, MappingProfile
from app.infrastructure.tasks import intelligent_parser_engine
from sqlalchemy.orm import joinedload
from pathlib import Path

def verify_fix():
    db = SessionLocal()
    try:
        job = db.query(ConversionJob).order_by(ConversionJob.created_at.desc()).first()
        if not job or not job.raw_data_path:
            print("No job or raw data found.")
            return

        print(f"Testing fix on Job {job.id}...")
        
        # Load Raw Data
        with open(job.raw_data_path, 'r') as f:
            raw_data = json.load(f)
        
        df = pd.DataFrame(raw_data)
        print(f"Loaded DataFrame with {len(df)} rows.")

        # Get Mapping Rules
        mapping_rules = {}
        if job.mapping_profile_id:
            profile = db.query(MappingProfile).options(joinedload(MappingProfile.mappings)).filter(MappingProfile.id == job.mapping_profile_id).first()
            if profile: mapping_rules = {m.source_code.upper(): m.target_status for m in profile.mappings}

        # Run Engine
        try:
            records = intelligent_parser_engine(
                df=df, 
                config=job.parsing_config, 
                year=job.attendance_year, 
                month=job.attendance_month, 
                mapping_rules=mapping_rules
            )
            print(f"Extracted Records: {len(records)}")
            if len(records) > 0:
                print("Sample Extracted Record:", records[0])
                
                # SAVE THE FIX TO THE FILE
                if job.processed_data_path:
                    with open(job.processed_data_path, "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2, ensure_ascii=False)
                    print(f"Successfully wrote {len(records)} records to {job.processed_data_path}")
            else:
                print("Still 0 records extracted.")
        except Exception as e:
            print(f"Engine failed: {e}")

    except Exception as e:
        print(f"Script error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_fix()
