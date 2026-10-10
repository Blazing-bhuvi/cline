"""Seed the demonstration database with clearly fictional voter records.

These records are synthetic and exist only for local demonstration. They are NOT
real voter data and are NOT sourced from any official electoral roll.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script directly from backend/scripts or elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.init_db import init_db  # noqa: E402
from app.database.session import get_session_local  # noqa: E402
from app.models.orm import VoterRecord  # noqa: E402

# Clearly fictional identifiers (3 letters + 7 digits) and names.
FICTIONAL_RECORDS: list[dict] = [
    {
        "epic_number": "XYZ0000001",
        "name": "Aarav Sharma",
        "relative_name": "Rohit Sharma",
        "gender": "male",
        "date_of_birth": "1990-04-12",
        "age": "35",
        "address": "12 MG Road, Bengaluru, Karnataka 560001",
    },
    {
        "epic_number": "XYZ0000002",
        "name": "Priya Patel",
        "relative_name": "Nilesh Patel",
        "gender": "female",
        "date_of_birth": "1988-11-03",
        "age": "37",
        "address": "45 Satellite Road, Ahmedabad, Gujarat 380015",
    },
    {
        "epic_number": "XYZ0000003",
        "name": "Rohan Iyer",
        "relative_name": "Suresh Iyer",
        "gender": "male",
        "date_of_birth": "1995-07-21",
        "age": "31",
        "address": "8 Anna Salai, Chennai, Tamil Nadu 600002",
    },
    {
        "epic_number": "XYZ0000004",
        "name": "Sneha Reddy",
        "relative_name": "Kiran Reddy",
        "gender": "female",
        "date_of_birth": "1993-02-17",
        "age": "33",
        "address": "22 Banjara Hills, Hyderabad, Telangana 500034",
    },
    {
        "epic_number": "XYZ0000005",
        "name": "Vikram Singh",
        "relative_name": "Rajendra Singh",
        "gender": "male",
        "date_of_birth": "1985-09-30",
        "age": "40",
        "address": "17 Connaught Place, New Delhi 110001",
    },
]


def seed(overwrite: bool = False) -> int:
    init_db()
    db = get_session_local()()
    added = 0
    try:
        if overwrite:
            db.query(VoterRecord).delete()
        for rec in FICTIONAL_RECORDS:
            exists = (
                db.query(VoterRecord)
                .filter(VoterRecord.epic_number == rec["epic_number"])
                .first()
            )
            if exists:
                continue
            db.add(
                VoterRecord(
                    epic_number=rec["epic_number"],
                    name=rec["name"],
                    relative_name=rec["relative_name"],
                    gender=rec["gender"],
                    date_of_birth=rec["date_of_birth"],
                    age=rec["age"],
                    address=rec["address"],
                    source="synthetic_demo",
                    verification_status="demo",
                )
            )
            added += 1
        db.commit()
    finally:
        db.close()
    return added


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic voter records.")
    parser.add_argument("--overwrite", action="store_true", help="Clear existing records first.")
    args = parser.parse_args()
    count = seed(overwrite=args.overwrite)
    print(f"Seeded {count} synthetic voter records.")
