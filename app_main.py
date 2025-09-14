from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from main import schedule_tasks
from user_input import get_user_input
import logging
import math
import datetime
import json        #這裏cody加
from pydantic import BaseModel
from typing import List, Dict, Any
from vertex_client import init_vertex_ai_client, connect_to_model, ask_vertex_ai
from AIRecommend.dickmain import schedule_plan_tasks  # 你的排程邏輯檔

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
#以下為cody加的部分
class AskRequest(BaseModel):
    question: str

@app.on_event("startup")
def startup_event():
    PROJECT_ID = "task-focus-4i2ic"
    LOCATION = "us-central1"

    if init_vertex_ai_client(PROJECT_ID, LOCATION):
        global model
        model = connect_to_model()
        if not model:
            raise RuntimeError("無法連接到模型")
    else:
        raise RuntimeError("初始化 Vertex AI 失敗")

@app.post("/dick/ask")
def ask_api(req: AskRequest):
    try:
        answer = ask_vertex_ai(model, req.question)
    
        # 嘗試抽取 JSON 部分
        start_idx = answer.find("{")
        end_idx = answer.rfind("}") + 1
        if start_idx == -1 or end_idx == -1:
            raise HTTPException(status_code=500, detail="找不到 JSON 部分")
        
        plan_json = json.loads(answer[start_idx:end_idx])

        # 推薦理由就是 JSON 前面的文字
        recommendation = answer[:start_idx].strip()

        return {
            "status": "ok",
            "recommendation": recommendation,
            "result": plan_json
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
class Task(BaseModel):
    事件: str
    年分: int
    月份: int
    日期: int
    開始時間: str
    結束時間: str
    多元智慧領域: str
    持續時間: Optional[int] = None  # 新增：持續時間（分鐘），可選字段

class SubmitPlan(BaseModel):
    計畫名稱: str
    已選行程: List[Task]

# 記憶體暫存使用者勾選的行程
saved_tasks: List[Dict[str, Any]] = []

def calculate_duration(start_time: str, end_time: str) -> int:
    """計算開始時間到結束時間的分鐘數"""
    try:
        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        
        # 如果結束時間小於開始時間，表示跨天
        if end_minutes < start_minutes:
            end_minutes += 24 * 60
            
        return end_minutes - start_minutes
    except Exception as e:
        logging.error(f"❌ 計算持續時間錯誤: {e}")
        return 60  # 預設 60 分鐘

@app.post("/dick/submit")
async def submit_plan(plan: SubmitPlan):
    try:
        logging.info(f"✅ 收到使用者勾選行程: {plan.dict()}")

        processed_tasks = []
        for task in plan.已選行程:
            task_dict = task.dict()

            # 如果前端有提供「持續時間」，直接使用；沒有就用開始/結束計算一次
            if task_dict.get('持續時間') is None:
                calculated_duration = calculate_duration(
                    task_dict['開始時間'],
                    task_dict['結束時間']
                )
                task_dict['持續時間'] = calculated_duration
                logging.info(f"🔍 自動計算 '{task_dict['事件']}' 持續時間: {calculated_duration} 分鐘")
            else:
                # 不再對比或覆蓋，完全信任前端數值
                logging.info(f"🔍 使用 JSON 提供的 '{task_dict['事件']}' 持續時間: {task_dict['持續時間']} 分鐘")

            processed_tasks.append(task_dict)

        saved_tasks.extend(processed_tasks)

        plan_dict = plan.dict()
        plan_dict['已選行程'] = processed_tasks
        logging.info(f"🔍 準備送入排程的資料: {plan_dict}")

        try:
            schedule_result = schedule_plan_tasks(plan_dict)
            logging.info(f"✅ 排程結果: {schedule_result}")
        except Exception as schedule_error:
            logging.error(f"❌ 排程錯誤: {schedule_error}")
            schedule_result = {"success": False, "message": f"排程失敗: {str(schedule_error)}"}

        return {
            "success": True,
            "message": "✅ 已收到、保存勾選行程，並完成自動排程",
            "count": len(saved_tasks),
            "submitted_tasks": processed_tasks,
            "schedule_result": schedule_result
        }

    except Exception as e:
        logging.error(f"❌ 儲存或排程行程錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"儲存或排程行程失敗: {str(e)}")

@app.get("/dick/submit")
async def get_saved_tasks():
    try:
        return {
            "success": True,
            "message": "✅ 已成功獲取儲存的行程",
            "count": len(saved_tasks),
            "saved_tasks": saved_tasks
        }
    except Exception as e:
        logging.error(f"❌ 獲取行程錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"獲取行程失敗: {str(e)}")