import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore

# ✅ Firebase 初始化（只需要執行一次）
if not firebase_admin._apps:
    cred = credentials.Certificate("/home/improj/jack_FastAPI/task-focus-4i2ic-3d473316080f.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

def _to_doc_name(itype: str, mapping: dict) -> str:
    s = str(itype).strip().lower()
    # 中文 → 英文後綴
    if s in mapping:
        suffix = mapping[s]
    else:
        # 已含 fatigue_ → 取後綴；否則直接當後綴
        suffix = s[len("fatigue_"):] if s.startswith("fatigue_") else s
    return f"fatigue_{suffix}"

def get_base_cost_from_firebase_new(intelligence_list: list):
    """
    新邏輯：前端已經傳「多元智慧領域」（英文）
    intelligence_list 範例: ["bodily_kinesthetic", "logical", "musical"]
    每個 intelligence 會對應 Firebase 中 fatigue_xxx 文件
    """
    CHINESE_TO_DOC_SUFFIX = {
        "語言智能": "linguistic",
        "邏輯數理智能": "logical",
        "空間智能": "spatial",
        "肢體動覺智能": "bodily_kinesthetic",
        "音樂智能": "musical",
        "人際關係智能": "interpersonal",
        "自省智能": "intrapersonal",
        "自然辨識智能": "naturalistic"
    }



    costs = []
    cache = {}

    for itype in intelligence_list:
        if not isinstance(itype, str):
            print(f"⚠️ 不支援的 intelligence 類型: {type(itype)}，跳過")
            continue

        doc_name = _to_doc_name(itype, CHINESE_TO_DOC_SUFFIX)
        print(f"🔎 查詢文件: {doc_name}")

        # 快取
        if doc_name in cache:
            costs.append(cache[doc_name])
            continue

        try:
            doc_ref = db.collection("users").document("testUser") \
                        .collection("fatigue_logs").document(doc_name)
            doc = doc_ref.get()

            if not doc.exists:
                print(f"⚠️ Firebase 文件不存在: {doc_name}，使用預設值")
                values = [0.5] * 24
            else:
                data = doc.to_dict() or {}
                values = data.get("values")
                if not isinstance(values, list):
                    print(f"⚠️ {doc_name} 的 values 欄位缺失或格式錯誤，使用預設值")
                    values = [0.5] * 24
                else:
                    values = [round(float(v), 1) for v in values]
                    # 補/截斷為 24
                    if len(values) < 24:
                        values = values + [values[-1]] * (24 - len(values))
                    else:
                        values = values[:24]

        except Exception as e:
            print(f"❌ 讀取 {doc_name} 失敗: {e}，使用預設值")
            values = [0.5] * 24

        cache[doc_name] = values
        costs.append(values)

    if not costs:
        print("⚠️ 未獲取任何成本資料，回傳全預設矩陣")
        costs = [[0.5] * 24 for _ in range(len(intelligence_list))]

    return np.array(costs)
