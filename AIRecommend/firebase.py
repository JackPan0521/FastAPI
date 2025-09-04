import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore

# ✅ Firebase 初始化（只需要執行一次）
if not firebase_admin._apps:
    cred = credentials.Certificate("C:/pydata/test/task-focus-4i2ic-3d473316080f.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

def get_base_cost_from_firebase_new(intelligence_list: list):
    """
    新邏輯：前端已經傳「多元智慧領域」（英文）
    intelligence_list 範例: ["bodily_kinesthetic", "logical", "musical"]
    每個 intelligence 會對應 Firebase 中 fatigue_xxx 文件
    """
    costs = []
    cache = {}

    for itype in intelligence_list:
        if not isinstance(itype, str):
            raise ValueError(f"❌ 不支援的 intelligence 類型: {type(itype)}")

        key = itype.strip().lower()
        doc_name = f"fatigue_{key}"

        # ✅ 快取避免重複 fetch
        if doc_name in cache:
            costs.append(cache[doc_name])
            continue

        # ✅ 從 Firestore 取 fatigue log
        doc_ref = db.collection("users").document("testUser") \
                    .collection("fatigue_logs").document(doc_name)
        doc = doc_ref.get()
        if not doc.exists:
            raise ValueError(f"❌ Firebase 文件 '{doc_name}' 不存在")

        data = doc.to_dict()
        if 'values' not in data or not isinstance(data['values'], list):
            raise ValueError(f"❌ 文件 '{doc_name}' 的 'values' 欄位不存在或格式錯誤")

        # ✅ 轉成 float 並四捨五入
        values = [round(float(v), 1) for v in data['values']]
        cache[doc_name] = values
        costs.append(values)

    if not costs:
        raise ValueError("❌ 未能從 Firebase 獲取任何成本資料")

    return np.array(costs)
