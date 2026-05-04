from fastapi import FastAPI
import asyncio
from scraper import run_all

app = FastAPI()

@app.get("/")
async def run():
    await run_all()
    return {"status": "ok"}
