import time
from app.db import SessionLocal
from app.services.audit import audit


def main():
    while True:
        db = SessionLocal()
        try:
            audit(db, "scheduler.heartbeat", "Scheduler heartbeat")
        finally:
            db.close()
        time.sleep(600)


if __name__ == "__main__":
    main()
