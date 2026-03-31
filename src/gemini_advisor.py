import os
import threading
import glob
from dotenv import load_dotenv
from google import genai
from google.genai import types

class GeminiAdvisor:
    def __init__(self):
        """面試戰術策劃大腦 - 綁定 Gemini 2.5 Flash 來達到最低延遲"""
        load_dotenv()
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ 警告：找不到 GEMINI_API_KEY 環境變數。請務必將它加進您的 .env 中。")
            
        self.client = genai.Client(api_key=api_key)
        
        # 實踐架構設計 B (術語校正) 與 C (極致精簡) 的終極 System Prompt
        self.system_instruction = """
您是一位正在輔助台灣專業人士與歐洲/德國企業進行「跨國遠端會議」的「資深 AI 秘密參謀」。
您的核心主旨是：取代傳統死板的 Cheatsheet（重點小抄），即時分析雙方的對話，給出戰術支援並預擬草稿，徹底消除使用者的外語對答緊張感。
對話可能混合英文或德文，但您的主要溝通句子「必須」是極簡繁體中文。

【術語校正清單 Glossary】
若看到以下拼字有誤或發音相近的字眼（受限於語音辨識誤差），請自動理解為：
- ASP ERP
- ACC
- TPC
- Blue Card
- DIN Standard

【輸出限制與排版法則 (絕對嚴格)】
為了讓與會者在一瞥之間取得戰局方向並能直接開口，您的回答「必須」嚴格分成以下兩個區塊（絕對不允許有其他的開場白或問候）：

[動態會議小抄]
- （繁體中文）**絕對嚴格限制為 1-2 點**，每點不可超過 12 個中文字。
- （繁體中文）僅提供核心戰略大方向，術語保持外文（如 ASP, ERP, TPC...）。
- （繁體中文）若無特殊陷阱，一律保持在 2 行以內，不要佔用過多空間。

[Suggested Script]
（英文）**這是最重要的部分，請確保它佔據最優位置。**
（英文）請直接給出一段「完美、道地且專業」的英文會議應答講稿。
（英文）字數約在 30 ~ 50 字以內，讓使用者能直接看著螢幕朗讀。
"""
        # 動態偵測並鎖定擁有最大免費額度的最佳模型
        self.model_name = self._get_optimal_model()

        # 動態載入使用者自訂的參考資料 (Profile, 專案背景等)
        context_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context")
        external_context = ""
        if os.path.exists(context_dir):
            for filepath in glob.glob(os.path.join(context_dir, "*.*")):
                if filepath.endswith(('.md', '.txt')):
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            filename = os.path.basename(filepath)
                            external_context += f"\n--- 參考文件: {filename} ---\n{f.read()}\n"
                    except Exception as e:
                        print(f"⚠️ 無法讀取參考資料 {filepath}: {e}")

        # 如果有讀取到使用者的背景資料，直接加進 AI 的大腦最深處
        if external_context:
            self.system_instruction += f"\n\n【與會者背景與商業資料 (極其重要，請依據這些資料提供最個人化的戰術與講稿)】\n{external_context}"

    def _get_optimal_model(self):
        """
        動態偵測帳號可用的 API 模型，並過濾掉那些「被 Google 嚴格限制配額 (如 20次/天)」的 Preview 版。
        根據歷史經驗，正式版 (非 Preview) 通常擁有 1500 RPD 的極大免費額度。
        """
        try:
            available_models = [m.name.replace('models/', '') for m in self.client.models.list()]
            
            # 優先順序：既然已綁卡解除免費層級限制，直接火力全開優先使用最新 2.5 版本
            preferences = [
                'gemini-3-flash',          # 最新一代的頂尖閃電版 (Gemini 3)
                'gemini-2.5-flash',        # 第 2.5 代閃電版
                'gemini-2.0-flash',        # 當今主力，額度最大 (1500)
                'gemini-1.5-flash',        # 廣泛相容的老將
                'gemini-1.5-flash-latest', 
                'gemini-flash-latest',     # 動態最新穩定版
                'gemini-2.0-flash-lite'    # 輕量版，額度更大
            ]
            
            for pref in preferences:
                if pref in available_models:
                    print(f"✅ [Gemini Advisor] 自動最佳化選定模型: {pref} (確保最大 API 額度)")
                    return pref
                    
            # 若偏好的清單都沒有，找出任何一個不是 preview 的 flash 模型
            for m_name in available_models:
                if 'flash' in m_name and 'preview' not in m_name:
                    print(f"⚠️ [Gemini Advisor] 自動使用備用模型: {m_name}")
                    return m_name
                    
            print(f"⚠️ [Gemini Advisor] 找不到理想模型，強制退回 gemini-2.0-flash")
            return 'gemini-2.0-flash' # 硬扛
            
        except Exception as e:
            print(f"⚠️ [Gemini Advisor] 模型自動探測失敗 ({e})，使用預設值 gemini-2.0-flash")
            return 'gemini-2.0-flash'

    def analyze_dialogue_async(self, dialogue_text, callback):
        """
        非同步呼叫 API，避免干擾本地端的語音錄製。
        呼叫成功後，將回傳結果直接塞給傳入的 callback 函數（未來交由 UI 畫面渲染）。
        """
        def worker():
            if not dialogue_text.strip():
                return
                
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=dialogue_text,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        temperature=0.3, # 低溫強制不廢話
                    )
                )
                callback(response.text.strip())
            except Exception as e:
                callback(f"⚠️ Gemini 請求錯誤: {e}")
                
        # 啟動並分離執行緒
        threading.Thread(target=worker, daemon=True).start()

    def analyze_dialogue_sync(self, dialogue_text):
        """
        同步版本的 API 呼叫 (適用於 Streamlit 這類本身就會循環渲染的框架)
        """
        if not dialogue_text.strip():
            return ""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=dialogue_text,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.3,
                )
            )
            return response.text.strip()
        except Exception as e:
            return f"⚠️ Gemini 請求錯誤: {e}"
