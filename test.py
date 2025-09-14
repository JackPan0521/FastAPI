'''import unittest
import os
import datetime
import json

# 假設你的原始程式碼在 `vertex_client.py` 檔案中
from vertex_client import init_vertex_ai_client, connect_to_model, ask_vertex_ai

class TestRealModelIntegration(unittest.TestCase):

    PROJECT_ID = "task-focus-4i2ic"
    LOCATION = "us-central1"
    ENDPOINT_ID = "8467368732316925952"

    @classmethod
    def setUpClass(cls):
        print("\n--- 開始設置集成測試環境 ---")
        print(f"嘗試初始化 Vertex AI (專案: {cls.PROJECT_ID}, 區域: {cls.LOCATION})...")

        init_success = init_vertex_ai_client(cls.PROJECT_ID, cls.LOCATION, key_path="task-focus-4i2ic-3d473316080f.json")
        if not init_success:
            # >>>>> 修正這裡：直接拋出 RuntimeError 或 unittest.SkipTest <<<<<
            raise RuntimeError("Vertex AI 初始化失敗。請確保已配置 ADC 或提供 my-key.json。")
        
        print(f"嘗試連接到實際模型端點: {cls.ENDPOINT_ID}...")
        cls.model = connect_to_model()
        if not cls.model:
            # >>>>> 修正這裡：直接拋出 RuntimeError 或 unittest.SkipTest <<<<<
            raise RuntimeError("無法連接到模型端點。請檢查 Endpoint ID、權限和網路連接。")
        print("--- 集成測試環境設置完成 ---")

    @classmethod
    def tearDownClass(cls):
        print("\n--- 清理集成測試環境 ---")
        cls.model = None
        print("--- 集成測試環境清理完成 ---")

    def test_01_generate_valid_plan(self):
        """
        測試模型是否能根據用戶需求生成一個有效的行程計畫，並符合 JSON 格式。
        """
        print("\n--- 執行測試: 生成有效計畫 ---")
        question = "幫我規劃一個下週一到週三，每天早上跑步30分鐘的健身計畫。"
        print(f"發送問題: {question}")
        response_text = ask_vertex_ai(self.__class__.model, question)
        print("收到模型回應:")
        print(response_text)

        self.assertIsNotNone(response_text, "模型回應不應為 None")
        self.assertIsInstance(response_text, str, "模型回應應為字串")

        try:
            response_data = json.loads(response_text)
            self.assertIn("計畫名稱", response_data, "回應 JSON 應包含 '計畫名稱'")
            self.assertIn("行程", response_data, "回應 JSON 應包含 '行程'")
            self.assertIsInstance(response_data["行程"], list, "行程應為列表")
            self.assertGreater(len(response_data["行程"]), 0, "行程列表不應為空")

            tomorrow = datetime.date.today() + datetime.timedelta(days=1)
            
            for i, event in enumerate(response_data["行程"]):
                self.assertIn("事件", event, f"行程事件 {i} 應包含 '事件'")
                self.assertIn("年分", event, f"行程事件 {i} 應包含 '年分'")
                self.assertIn("月份", event, f"行程事件 {i} 應包含 '月份'")
                self.assertIn("日期", event, f"行程事件 {i} 應包含 '日期'")
                self.assertIn("持續時間", event, f"行程事件 {i} 應包含 '持續時間'")
                self.assertIn("多元智慧領域", event, f"行程事件 {i} 應包含 '多元智慧領域'")
                self.assertIsInstance(event["持續時間"], int, f"行程事件 {i} 的 '持續時間' 應為整數")
                self.assertGreater(event["持續時間"], 0, f"行程事件 {i} 的 '持續時間' 應大於 0")
                self.assertRegex(event["多元智慧領域"], r"fatigue_.*", f"行程事件 {i} 的 '多元智慧領域' 應有 'fatigue_' 前綴")

                # 驗證日期是否合理 (至少是明天或之後)
                event_date = datetime.date(event["年分"], event["月份"], event["日期"])
                self.assertGreaterEqual(event_date, tomorrow, f"行程事件 {i} 的日期 {event_date} 應從明天 {tomorrow} 開始或之後")

        except json.JSONDecodeError as e:
            self.fail(f"模型回傳的內容不是有效的 JSON 格式: {e}\n原始回應: {response_text}")
        except AssertionError as e:
            self.fail(f"JSON 格式或內容驗證失敗: {e}\n原始回應: {response_text}")
        print("--- 測試結束: 生成有效計畫 (成功) ---")

    def test_02_handle_out_of_scope_question(self):
        """
        測試模型是否能正確處理超出其行程規劃範圍的問題。
        """
        print("\n--- 執行測試: 處理超出範圍問題 ---")
        question = "請幫我寫一首關於貓的詩。"
        print(f"發送問題: {question}")
        response_text = ask_vertex_ai(self.__class__.model, question)
        print("收到模型回應:")
        print(response_text)

        self.assertIsNotNone(response_text, "模型回應不應為 None")
        self.assertIsInstance(response_text, str, "模型回應應為字串")
        self.assertEqual(response_text.strip(), "這個問題超出我的行程規劃範圍。", "模型應回傳超出範圍的標準訊息")
        print("--- 測試結束: 處理超出範圍問題 (成功) ---")


if __name__ == '__main__':
    unittest.main()'''