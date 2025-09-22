import numpy as np
import math
from scipy.optimize import milp, LinearConstraint, Bounds
from recommend_firebase import get_base_cost_from_firebase_new, db
import json
import recommend_user_input


def write_results_to_firebase(uid: str, date_str: str, schedule_results: list):
    """
    寫入 Firebase: /Tasks/{uid}/task_list/{date}/tasks/{idx}
    """
    date_key = date_str
    for idx, task in enumerate(schedule_results):
        try:
            db.collection("Tasks").document(uid) \
              .collection("task_list").document(date_key) \
              .collection("tasks").document(str(idx)) \
              .set(task, merge=True)
            print(f"✅ 成功寫入任務 {idx} (日期: {date_key}, UID: {uid})")
        except Exception as e:
            print(f"❌ 寫入任務 {idx} 發生錯誤:", e)


def schedule_plan_tasks(plan_json):
    print("📥 收到排程請求 JSON:", plan_json)
    print(f"📥 輸入類型: {type(plan_json)}")

    # 類型檢查和轉換
    if isinstance(plan_json, str):
        try:
            plan_json = json.loads(plan_json)
            print("🔄 已將字符串轉換為字典")
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析錯誤: {e}")
            return {"success": False, "message": f"JSON 解析錯誤: {str(e)}"}

    if not isinstance(plan_json, dict):
        print(f"❌ 輸入不是字典: {type(plan_json)}")
        return {"success": False, "message": f"輸入類型錯誤: {type(plan_json)}"}

    tasks = plan_json.get("已選行程", [])
    if not tasks:
        print("❌ 沒有任務可以排程")
        return {"success": False, "message": "沒有任務可以排程"}

    try:
        # === 解析任務數據 ===
        durations = []  # 任務持續時間（5分鐘單位）
        desc_list = []
        intelligence_list = []
        date_list = []
        time_windows = []
        uid = tasks[0].get("uid", "unknown")  # 從第一個任務拿 uid

        for i, t in enumerate(tasks):
            print(f"🔍 處理任務 {i}: {t.get('事件')}")

            if not isinstance(t, dict):
                print(f"❌ 任務 {i} 不是字典類型: {type(t)}")
                continue

            # 持續時間 → 5 分鐘單位
            duration_minutes = t.get("持續時間", 60)
            duration_slots = math.ceil(duration_minutes / 5)
            durations.append(duration_slots)

            # 可用時間窗口
            start_time_str = t.get("開始時間", "00:00")
            end_time_str = t.get("結束時間", "23:59")

            sh, sm = map(int, start_time_str.split(":"))
            eh, em = map(int, end_time_str.split(":"))

            start_hour = sh + sm / 60
            end_hour = eh + em / 60
            if end_hour <= start_hour:  # 跨天
                end_hour += 24

            time_windows.append((start_hour, end_hour))

            desc_list.append(t.get("事件", ""))
            intelligence_list.append(t.get("多元智慧領域", "general"))
            date_list.append(f"{t['年分']}-{t['月份']:02d}-{t['日期']:02d}")

            print(f"✅ 任務 {i}: {t.get('事件')}")
            print(f"   📅 日期: {date_list[-1]}")
            print(f"   ⏰ 可用時間窗口: {start_time_str}-{end_time_str} ({start_hour:.2f}-{end_hour:.2f})")
            print(f"   ⏱️ 持續時間: {duration_minutes} 分鐘 ({duration_slots} 槽)")

        n = len(durations)
        print(f"⏱ 共有 {n} 個任務需要排程")

        # === 成本矩陣 ===
        slots_per_hour = 12
        total_slots = 24 * slots_per_hour

        try:
            base_cost = get_base_cost_from_firebase_new(intelligence_list)
            print(f"✅ 成功獲取成本矩陣，形狀: {base_cost.shape}")
        except Exception as cost_error:
            print(f"⚠️ 成本矩陣失敗: {cost_error}，使用預設")
            base_cost = np.ones((len(intelligence_list), 24)) * 0.5

        extended_cost = np.repeat(base_cost, slots_per_hour, axis=1)[:, :total_slots]
        if n > base_cost.shape[0]:
            repeat_times = math.ceil(n / base_cost.shape[0])
            C = np.tile(extended_cost, (repeat_times, 1))[:n, :]
        else:
            C = extended_cost[:n, :]

        # === MILP 建立變數 ===
        num_vars = 0
        task_var_ranges = []
        for i in range(n):
            task_start_slots = int(time_windows[i][0] * slots_per_hour)
            task_end_slots   = int(time_windows[i][1] * slots_per_hour)
            task_time_slots = (task_end_slots - task_start_slots + 1) - durations[i] + 1
            if task_time_slots <= 0:
                return {"success": False, "message": f"任務 {i} 時間窗口不足"}
            task_var_ranges.append((num_vars, num_vars + task_time_slots))
            num_vars += task_time_slots

        bounds = Bounds([0] * num_vars, [1] * num_vars)
        integrality = np.ones(num_vars, dtype=bool)

        # === 每任務必須排一次 ===
        A_eq, b_eq = [], []
        for i in range(n):
            row = [0] * num_vars
            start_var, end_var = task_var_ranges[i]
            for j in range(start_var, end_var):
                row[j] = 1
            A_eq.append(row)
            b_eq.append(1)

        # === 避免重疊 ===
        A_ub, b_ub = [], []
        for p in range(n):
            for q in range(p + 1, n):
                p_start_slots = int(time_windows[p][0] * slots_per_hour)
                q_start_slots = int(time_windows[q][0] * slots_per_hour)
                p_start_var, p_end_var = task_var_ranges[p]
                q_start_var, q_end_var = task_var_ranges[q]
                for jp in range(p_start_var, p_end_var):
                    Sp = p_start_slots + (jp - p_start_var)
                    for jq in range(q_start_var, q_end_var):
                        Sq = q_start_slots + (jq - q_start_var)
                        if (Sp < Sq + durations[q] and Sq < Sp + durations[p]):
                            row = [0] * num_vars
                            row[jp] = 1
                            row[jq] = 1
                            A_ub.append(row)
                            b_ub.append(1)

        # === 成本函數 ===
        c = []
        for i in range(n):
            task_start_slots = int(time_windows[i][0] * slots_per_hour)
            start_var, end_var = task_var_ranges[i]
            for j in range(start_var, end_var):
                actual_start_slot = task_start_slots + (j - start_var)
                total_cost = sum(C[i][actual_start_slot + t] for t in range(durations[i]))
                c.append(total_cost)
        c = np.array(c)

        # === 求解 MILP ===
        constraints = [LinearConstraint(A_eq, b_eq, b_eq)]
        if A_ub:
            constraints.append(LinearConstraint(A_ub, [-np.inf] * len(b_ub), b_ub))
        res = milp(c=c, constraints=constraints, bounds=bounds, integrality=integrality)

        if res.success:
            scheduled_tasks = []
            for i in range(n):
                task_start_slots = int(time_windows[i][0] * slots_per_hour)
                start_var, end_var = task_var_ranges[i]
                for j in range(start_var, end_var):
                    if res.x[j] > 0.5:
                        actual_start_slot = task_start_slots + (j - start_var)
                        actual_end_slot = actual_start_slot + durations[i]
                        sh, sm = divmod(actual_start_slot * 5, 60)
                        eh, em = divmod(actual_end_slot * 5, 60)
                        scheduled_tasks.append({
                            "index": i,
                            "date": date_list[i],
                            "startTime": f"{sh:02d}:{sm:02d}",
                            "endTime": f"{eh:02d}:{em:02d}",
                            "desc": desc_list[i],
                            "intelligence": intelligence_list[i]
                        })
                        break

            # ✅ 正確呼叫 Firebase 寫入
            write_results_to_firebase(uid, date_list[0], scheduled_tasks)

            return {"success": True, "scheduled_tasks": scheduled_tasks, "total_cost": float(np.dot(c, res.x))}
        else:
            return {"success": False, "message": "MILP 找不到可行解"}

    except Exception as e:
        return {"success": False, "message": f"排程處理錯誤: {str(e)}"}
