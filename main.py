import numpy as np
import math
from scipy.optimize import milp, LinearConstraint, Bounds
from firebase import get_base_cost_from_firebase, db
from fine_tuningAPI import intelligent_task_analysis
from datetime import datetime
from firebase import get_all_schedule
import logging

def write_results_to_firebase(uid: str, date_str: str, schedule_results):
    tasks_ref = db.collection("Tasks").document(uid) \
                  .collection("task_list").document(date_str) \
                  .collection("tasks")
    existing_tasks = {doc.id: doc.to_dict() for doc in tasks_ref.stream()}

    for idx, task in enumerate(schedule_results):
        task_key = f"{task['desc']}-{task['startTime']}"
        if task_key in existing_tasks:
            logging.info(f"⚠️ 任務已存在，跳過: {task_key}")
            continue
        tasks_ref.document(str(idx)).set(task, merge=True)
        logging.info(f"✅ 成功寫入任務 {idx}: {task}")

def schedule_tasks(Ts, Te, durations, date_str, desc_list, uid: str = "testUser"):
    logging.info(f"執行 schedule_tasks，參數: Ts={Ts}, Te={Te}, durations={durations}, date_str={date_str}, uid={uid}")
    slots_per_hour = 12
    Ts_slots = int(Ts * slots_per_hour)
    Te_slots = int(Te * slots_per_hour)
    time_slots = Te_slots - Ts_slots
    n = len(durations)
    total_slots = 24 * slots_per_hour

    intelligent_analysis_results = intelligent_task_analysis(desc_list)#分類8大智能(陣列形式)

    base_cost = get_base_cost_from_firebase(intelligent_analysis_results)#把分類完的陣列輸入去firebase去抓對應的疲勞度
    #目前不確定抓回來的樣子會長怎樣
    extended_cost = np.repeat(base_cost, slots_per_hour, axis=1)[:, :total_slots]

    if n > base_cost.shape[0]:
        repeat_times = math.ceil(n / base_cost.shape[0])
        C = np.tile(extended_cost, (repeat_times, 1))[:n, :]
    else:
        C = extended_cost[:n, :]

    num_vars = n * time_slots
    bounds = Bounds([0] * num_vars, [1] * num_vars)
    integrality = np.ones(num_vars, dtype=bool)

    # get_today = datetime.now().strftime("%Y-%m-%d")
    all_schedule=get_all_schedule(date_str,uid)
    print("test:",all_schedule)
    if all_schedule is not None:
        print("not first time")        
        b_ub=cant_used_time(all_schedule,Ts_slots,Te_slots)
        A_ub = [[0] * num_vars for _ in range(time_slots)] 
        var_idx = 0
        for i in range(n):
            for j in range(time_slots):
                if j + durations[i] <= time_slots:
                    # 變數 x_ij 會佔用從 j 到 j + durations[i] - 1 的時段
                    for t in range(durations[i]):
                        slot_idx = j + t
                        A_ub[slot_idx][var_idx] = 1 # 標記變數 var_idx 會使用 slot_idx
                var_idx += 1
    else:
        print("first time")
        A_ub, b_ub = [], []
        for p in range(n):
            for q in range(p + 1, n):
                for jp in range(time_slots):
                    if jp + durations[p] > time_slots:
                        continue
                    Sp = Ts_slots + jp
                    for jq in range(time_slots):
                        if jq + durations[q] > time_slots:
                            continue
                        Sq = Ts_slots + jq
                        if Sp < Sq + durations[q] and Sq < Sp + durations[p]:
                            row = [0] * num_vars
                            row[p * time_slots + jp] = 1
                            row[q * time_slots + jq] = 1
                            A_ub.append(row)
                            b_ub.append(1)
    


    A_eq, b_eq = [], []
    for i in range(n):
        row = [0] * num_vars
        for j in range(time_slots):
            if j + durations[i] <= time_slots:
                row[i * time_slots + j] = 1
        A_eq.append(row)
        b_eq.append(1)


    

    c = []
    for i in range(n):
        for j in range(time_slots):
            if j + durations[i] > time_slots:
                c.append(1e6)
            else:
                total_cost = sum(C[i][Ts_slots + j + t] for t in range(durations[i]))
                c.append(total_cost)
    c = np.array(c)

    constraints = [LinearConstraint(A_eq, b_eq, b_eq)]
    if A_ub:
        constraints.append(LinearConstraint(A_ub, [-np.inf] * len(b_ub), b_ub))

    res = milp(c=c, constraints=constraints, bounds=bounds, integrality=integrality)

    if res.success:
        print(f"\n✅ 最佳解找到！（Ts={Ts:.2f}, Te={Te:.2f}）")
        X = res.x.reshape((n, time_slots))
        scheduled_tasks = []

        for i in range(n):
            for j in range(time_slots):
                if X[i][j] > 0.5:
                    start = Ts_slots + j
                    end = min(start + durations[i], Te_slots)  # ✅ 不超過 Te_slots
                    sh, sm = divmod(start * 5, 60)
                    eh, em = divmod(end * 5, 60)
                    if eh >= 24:  # 防止跨日
                        eh -= 24
                    start_str = f"{sh:02}:{sm:02}"
                    end_str = f"{eh:02}:{em:02}"
                    scheduled_tasks.append({
                        "index": i,
                        "startTime": start_str,
                        "endTime": end_str,
                        "desc": desc_list[i] if i < len(desc_list) else "",
                        "intelligence": intelligent_analysis_results[i].get("intelligence", "") if i < len(intelligent_analysis_results) else ""
                    })
                    break

        print("\n💰 最小總成本:", np.dot(c, res.x))
        print("最優解:", scheduled_tasks)
        # # 找到新任務的索引
        # for new_task in scheduled_tasks:
        #     index_in_sorted = all_tasks_sorted.index(new_task)
        #     print(f"新任務 {new_task['desc']} 在排序後的位置: {index_in_sorted}")
        # 合併新任務與當天所有任務
        all_tasks = all_schedule + scheduled_tasks
        print("all_tasks:", all_tasks)
        # 按照 startTime 排序
        all_tasks_sorted = sorted(all_tasks, key=lambda x: x['startTime'])
        for idx, task in enumerate(all_tasks_sorted):
            task['index'] = idx

        # 確認排序後的任務及其索引
        print("排序後的任務及索引:")
        for task in all_tasks_sorted:
            print(f"Index: {task['index']}, StartTime: {task['startTime']}, Desc: {task.get('desc', '')}")

        write_results_to_firebase(uid, date_str, all_tasks_sorted)  # 傳入 uid

        return all_tasks_sorted
    else:
        print("\n❌ 找不到可行解。")
        return None

def cant_used_time(all_schedule, fixed_Ts_slots, fixed_Te_slots):
    print("cant_used_time:", all_schedule)
    b = [1] * (fixed_Te_slots - fixed_Ts_slots )   # 預設每個 slot 的容量是 1
    slots_per_hour = 12

    for i in range(len(all_schedule)):
        try:
            # 確保 startTime 和 endTime 是字串
            start_time = all_schedule[i]['startTime']
            end_time = all_schedule[i]['endTime']
            if not isinstance(start_time, str) or not isinstance(end_time, str):
                raise ValueError(f"startTime 或 endTime 格式錯誤: {all_schedule[i]}")

            fixed_start_slot = time_to_slots(start_time)
            fixed_end_slot = time_to_slots(end_time)
        except ValueError as e:
            print(f"❌ 時間轉換錯誤: {e}")
            continue

        fixed_start_hour, fixed_start_minute = map(int, start_time.split(":"))
        fixed_end_hour, fixed_end_minute = map(int, end_time.split(":"))
        fixed_start = fixed_start_hour + fixed_start_minute / 60
        fixed_end = fixed_end_hour + fixed_end_minute / 60

        # 轉換成 slot index
        fixed_start_slots = int(fixed_start * slots_per_hour)
        fixed_end_slots = int(fixed_end * slots_per_hour)

        # --- 新增判斷是否有交集 ---
        if fixed_end_slots < fixed_Ts_slots or fixed_start_slots > fixed_Te_slots:
            continue  # 沒有落在 Ts~Te 內，跳過

        # --- 調整跨 Ts / Te 的情況 ---
        adj_start = max(fixed_start_slots, fixed_Ts_slots)
        adj_end = min(fixed_end_slots, fixed_Te_slots)

        # 標記被佔用的 slot
        for s in range(adj_start, adj_end ):
            b[s - fixed_Ts_slots] = 0
    print("b陣列:", b)

    return b

def time_to_slots(time_value, slots_per_hour=12):
    """將時間轉換成 slot 格數 (支援 float 小時數或 'HH:MM' 字串)"""
    if isinstance(time_value, str):
        if ":" not in time_value or not time_value.strip():
            raise ValueError(f"無效的時間字串: '{time_value}'")
        try:
            h, m = map(int, time_value.split(":"))
            return h * slots_per_hour + m // 5
        except ValueError:
            raise ValueError(f"時間字串格式錯誤: '{time_value}'")
    elif isinstance(time_value, (int, float)):
        # 如果是整數或浮點數，假設它是小時數，直接轉換
        return int(time_value * slots_per_hour)
    else:
        raise ValueError(f"time_value 必須是字串 'HH:MM' 或 float 小時數，收到: {type(time_value)}")
