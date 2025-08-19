from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from main import schedule_tasks
from user_input import get_user_input
import logging
import math
import datetime

app = FastAPI()
logging.basicConfig(level=logging.INFO)

class InputData(BaseModel):
    taskDate: str
    Ts: str
    Te: str
    n: int
    k: List[int]
    desc: List[str]

latest_data: Optional[InputData] = None

@app.get("/")
async def root():
    return {"message": "後端運行中。請使用 POST /api/submit 傳送資料"}

@app.get("/api/submit")
async def submit_get():
    return {"message": "請用 POST 傳送 JSON：{taskDate, Ts, Te, n, k, desc}"}

@app.post("/api/submit")
async def submit_and_compute(data: InputData):
    global latest_data
    latest_data = data
    logging.info(f"✅ 接收到資料: {data.dict()}")

    try:
        # 將接收到的資料送到 get_user_input 處理（你也可以直接拆開不用 get_user_input）
        Ts_hour, Ts_minute = map(int, data.Ts.split(":"))
        Te_hour, Te_minute = map(int, data.Te.split(":"))
        Ts = Ts_hour + Ts_minute / 60
        Te = Te_hour + Te_minute / 60
        if Te <= Ts:
            Te += 24
        durations = [math.ceil(d / 5) for d in data.k]
        date_str = data.taskDate or datetime.now().strftime("%Y-%m-%d")

        # 開始執行排程並寫入 Firebase
        schedule_tasks(Ts, Te, durations, date_str, data.desc)

        return {"success": True, "message": "✅ 任務成功排程並寫入 Firebase"}

    except Exception as e:
        logging.error(f"❌ 錯誤: {e}")
        return {"success": False, "error": str(e)}
    
@app.get("/api/latest")
async def get_latest_data():
    if latest_data is None:
        return {"message": "尚未有任何上傳的資料"}
    return latest_data.dict()