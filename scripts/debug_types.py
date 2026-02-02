# scripts/debug_types.py - Dev utility: list instrument types from database

from database import get_connection, initialize_db, CalibrationRepository


def main():
    conn = get_connection()
    initialize_db(conn)  # run schema + seeding
    repo = CalibrationRepository(conn)

    types = repo.list_instrument_types()
    print(f"Found {len(types)} instrument types:")
    for t in types:
        print(f"  {t['id']}: {t['name']}")


if __name__ == "__main__":
    main()
