import requests
import math

def get_plan_input():
    try:
        url = "https://f8e827554f9d.ngrok-free.app/dick/submit"  # 🚨 換成你的新 API
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        print("✅ API 請求成功，HTTP 狀態碼:", response.status_code)

        data = response.json()
        print("📥 從 API 取得原始計畫資料：", data)

        plan_name = data.get("計畫名稱", "未命名計畫")
        tasks = data.get("已選行程", [])

        parsed_tasks = []
        for idx, task in enumerate(tasks):
            try:
                # 解析日期
                date_str = f"{task['年分']}-{task['月份']:02}-{task['日期']:02}"
                # 持續時間換成「以 5 分鐘為單位」
                duration = math.ceil(task.get("持續時間", 0) / 5)

                parsed_tasks.append({
                    "event": task.get("事件", ""),
                    "date": date_str,
                    "duration": duration,
                    "intelligence": task.get("多元智慧領域", "").strip().lower(),
                    "start_time": task.get("開始時間", ""),
                    "end_time": task.get("結束時間", "")
                })
            except Exception as inner_e:
                print(f"⚠️ 解析第 {idx+1} 個任務失敗: {inner_e}")

        print(f"✅ 成功解析計畫 '{plan_name}'，共 {len(parsed_tasks)} 個任務")
        return plan_name, parsed_tasks

    except requests.exceptions.RequestException as req_e:
        print("❌ API 請求失敗：", req_e)
        return None, []
    except ValueError as val_e:
        print("❌ JSON 解析失敗：", val_e)
        return None, []
    except Exception as e:
        print("❌ 取得或解析 API 計畫資料時發生未知錯誤：", e)
        return None, []