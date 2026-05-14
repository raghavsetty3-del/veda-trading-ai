import time
from app.db import SessionLocal
from app.services.audit import audit


def main():
    while True:
        db = SessionLocal()
        try:
            audit(db, "worker.heartbeat", "Worker heartbeat")
        finally:
            db.close()
        time.sleep(300)


if __name__ == "__main__":
    main()
