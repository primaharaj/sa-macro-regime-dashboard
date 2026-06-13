import typer
from src.data_loader import load_fred

app = typer.Typer()

@app.command()
def fred(series_id: str, table: str):
    load_fred(series_id, table)
    print(f"Loaded {series_id} -> {table}")

if __name__ == "__main__":
    app()