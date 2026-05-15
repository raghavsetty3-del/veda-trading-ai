from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_additive_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "paper_trades" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("paper_trades")}
    dialect = engine.dialect.name
    float_type = "DOUBLE PRECISION" if dialect == "postgresql" else "FLOAT"
    timestamp_type = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"

    additions = {
        "exit_price": float_type,
        "exit_reason": "TEXT",
        "closed_at": timestamp_type,
        "realized_pnl": float_type,
        "r_multiple": float_type,
    }

    with engine.begin() as connection:
        for column_name, column_type in additions.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE paper_trades ADD COLUMN {column_name} {column_type}"))
