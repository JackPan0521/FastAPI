import numpy as np
import math
from scipy.optimize import milp, LinearConstraint, Bounds
from recommend_firebase import get_base_cost_from_firebase_new, db
import json
import recommend_user_input


def write_results_to_firebase(date_str, schedule_results):
    year, month, day = date_str.split("-")
    for idx, task in enumerate(schedule_results):
        try:
            db.collection("tasks").document(year) \
              .collection(month).document(day) \
              .collection("task_list").document(str(idx)) \
              .set(task, merge=True)
            print(f"✅ 成功寫入任務 {idx} 資料 (日期: {date_str})")
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
        durations = []  # 實際任務持續時間（5分鐘單位）
        desc_list = []
        intelligence_list = []
        date_list = []
        time_windows = []  # 可用時間窗口
        
        for i, t in enumerate(tasks):
            print(f"🔍 處理任務 {i}: {t.get('事件')}")
            
            if not isinstance(t, dict):
                print(f"❌ 任務 {i} 不是字典類型: {type(t)}")
                continue
            
            # 實際任務持續時間（以5分鐘為單位）
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
            
            # 處理跨天情況
            if end_hour <= start_hour:
                end_hour += 24
            
            time_windows.append((start_hour, end_hour))
            
            desc_list.append(t.get("事件", ""))
            intelligence_list.append(t.get("多元智慧領域", "general"))
            date_list.append(f"{t['年分']}-{t['月份']:02d}-{t['日期']:02d}")
            
            print(f"✅ 任務 {i}: {t.get('事件')}")
            print(f"   📅 日期: {date_list[-1]}")
            print(f"   ⏰ 可用時間窗口: {start_time_str}-{end_time_str} ({start_hour:.2f}-{end_hour:.2f})")
            print(f"   ⏱️ 實際持續時間: {duration_minutes}分鐘 ({duration_slots}槽)")

        n = len(durations)
        print(f"⏱ 共有 {n} 個任務需要排程")

        # === 不再計算全域時間範圍（每個任務用自己的時間窗口）===
        slots_per_hour = 12
        total_slots = 24 * slots_per_hour

        try:
            base_cost = get_base_cost_from_firebase_new(intelligence_list)  # e.g. ['fatigue_intrapersonal', ...]
            print(f"✅ 成功獲取成本矩陣，形狀: {base_cost.shape}")
        except Exception as cost_error:
            print(f"⚠️ 獲取成本矩陣失敗: {cost_error}，使用預設成本")
            base_cost = np.ones((len(intelligence_list), 24)) * 0.5

        extended_cost = np.repeat(base_cost, slots_per_hour, axis=1)[:, :total_slots]

        if n > base_cost.shape[0]:
            repeat_times = math.ceil(n / base_cost.shape[0])
            C = np.tile(extended_cost, (repeat_times, 1))[:n, :]
        else:
            C = extended_cost[:n, :]

        # === MILP 設定：為每個任務只在自己的時間窗口建立變數 ===
        num_vars = 0
        task_var_ranges = []

        for i in range(n):
            task_start_slots = int(time_windows[i][0] * slots_per_hour)
            task_end_slots   = int(time_windows[i][1] * slots_per_hour)

            # 在窗口內可放置的「開始位置」數量 = 可用槽數 - 任務長度 + 1
            task_time_slots = (task_end_slots - task_start_slots + 1) - durations[i] + 1

            if task_time_slots <= 0:
                print(f"❌ 任務 {i} 時間窗口不足: 需要 {durations[i]} 槽")
                return {"success": False, "message": f"任務 {i} 時間窗口不足"}

            task_var_ranges.append((num_vars, num_vars + task_time_slots))
            print(f"🔍 任務 {i} 變數範圍: {task_var_ranges[-1][0]}-{task_var_ranges[-1][1]-1} (共 {task_time_slots} 個變數)")
            num_vars += task_time_slots

        bounds = Bounds([0] * num_vars, [1] * num_vars)
        integrality = np.ones(num_vars, dtype=bool)

        # === 約束條件：每個任務必須排一次 ===
        A_eq, b_eq = [], []
        for i in range(n):
            row = [0] * num_vars
            start_var, end_var = task_var_ranges[i]
            for j in range(start_var, end_var):
                row[j] = 1
            A_eq.append(row)
            b_eq.append(1)

        # === 約束條件：避免任務重疊 ===
        A_ub, b_ub = [], []
        
        for p in range(n):
            for q in range(p + 1, n):
                p_start_slots = int(time_windows[p][0] * slots_per_hour)
                q_start_slots = int(time_windows[q][0] * slots_per_hour)
                
                p_start_var, p_end_var = task_var_ranges[p]
                q_start_var, q_end_var = task_var_ranges[q]
                
                for jp in range(p_start_var, p_end_var):
                    jp_actual = jp - p_start_var
                    Sp = p_start_slots + jp_actual
                    
                    for jq in range(q_start_var, q_end_var):
                        jq_actual = jq - q_start_var
                        Sq = q_start_slots + jq_actual
                        
                        # 檢查是否重疊
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
                j_actual = j - start_var
                actual_start_slot = task_start_slots + j_actual
                
                # 計算這個時段的總成本
                total_cost = sum(C[i][actual_start_slot + t] for t in range(durations[i]))
                c.append(total_cost)

        c = np.array(c)

        # === 求解 MILP ===
        constraints = [LinearConstraint(A_eq, b_eq, b_eq)]
        if A_ub:
            constraints.append(LinearConstraint(A_ub, [-np.inf] * len(b_ub), b_ub))

        print("🔹 開始 MILP 求解...")
        res = milp(c=c, constraints=constraints, bounds=bounds, integrality=integrality)

        if res.success:
            print(f"✅ MILP 求解成功！")
            scheduled_tasks = []

            for i in range(n):
                task_start_slots = int(time_windows[i][0] * slots_per_hour)
                start_var, end_var = task_var_ranges[i]
                
                for j in range(start_var, end_var):
                    if res.x[j] > 0.5:
                        j_actual = j - start_var
                        actual_start_slot = task_start_slots + j_actual
                        actual_end_slot = actual_start_slot + durations[i]
                        
                        sh, sm = divmod(actual_start_slot * 5, 60)
                        eh, em = divmod(actual_end_slot * 5, 60)
                        start_str = f"{sh:02d}:{sm:02d}"
                        end_str = f"{eh:02d}:{em:02d}"

                        scheduled_tasks.append({
                            "index": i,
                            "date": date_list[i],
                            "startTime": start_str,
                            "endTime": end_str,
                            "desc": desc_list[i],
                            "intelligence": intelligence_list[i],
                            "window": f"{time_windows[i][0]:.2f}-{time_windows[i][1]:.2f}"
                        })
                        print(f"📅 任務 {i+1}: {desc_list[i]}")
                        print(f"   🕐 安排時間: {start_str}-{end_str}")
                        print(f"   📋 可用窗口: {time_windows[i][0]:.2f}-{time_windows[i][1]:.2f}")
                        break

            print("📌 所有任務排程完成")
            print("💰 最小總成本:", np.dot(c, res.x))

            # 寫入 Firebase
            try:
                for task in scheduled_tasks:
                    write_results_to_firebase(task["date"], [task])
                print("✅ 全部任務已寫入 Firebase")
            except Exception as firebase_error:
                print(f"⚠️ Firebase 寫入部分失敗: {firebase_error}")

            return {
                "success": True,
                "message": "排程成功完成",
                "scheduled_tasks": scheduled_tasks,
                "total_cost": float(np.dot(c, res.x))
            }
        else:
            print("❌ MILP 找不到可行解")
            return {"success": False, "message": "MILP 找不到可行解"}

    except Exception as e:
        print(f"❌ 排程處理錯誤: {e}")
        return {"success": False, "message": f"排程處理錯誤: {str(e)}"}
