import os
import threading
import glob
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

class GeminiAdvisor:
    def __init__(self):
        """會議戰術策劃大腦 - 專為遠端技術對話與戰略決策優化"""
        load_dotenv()
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ 警告：找不到 GEMINI_API_KEY 環境變數。請務必將它加進您的 .env 中。")
            
        self.client = genai.Client(api_key=api_key)
        
        # 核心指令
        self.system_instruction = """
您是一位正在輔助「資深軟體架構師」進行「專業遠端會議」或「技術戰略對話」的「資深 AI 秘密參謀」。
您的核心主旨是：即時分析對話，提供精確的技術洞察與應對草稿，消除使用者在處理複雜議題時的瞬時壓力。
您不僅是翻譯或小抄，您是「顧問」，必須以「資深技術管理者」的視角提供建議。
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
- （繁體中文）提供核心戰略大方向或技術關鍵字，保持術語外文（如 ASP, ERP, TPC...）。
- （繁體中文）若無特殊陷阱，一律保持在 2 行以內，不要佔用過多空間。

[Suggested Script]
（英文）**這是最重要的部分，請確保它佔據最優位置。**
（英文）請直接給出一段「完美、道地且具備架構師厚度」的專業會議/對話應答講稿。
（英文）字數約在 30 ~ 50 字以內，讓使用者能直接看著螢幕朗讀。
"""
        # 模型選取
        self.model_name = self._get_optimal_model()

        # ==========================================================
        # ⚡️ [產品級優化]：載入上下文與建立本地「救命小抄」索引
        # ==========================================================
        context_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context")
        external_context = ""
        self.qa_index = []
        
        if os.path.exists(context_dir):
            for filepath in glob.glob(os.path.join(context_dir, "*.*")):
                if filepath.endswith(('.md', '.txt')):
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            filename = os.path.basename(filepath)
                            external_context += f"\n--- 參考文件: {filename} ---\n{content}\n"
                    except Exception as e:
                        print(f"⚠️ 無法讀取參考資料 {filepath}: {e}")
            
            # 特別針對 qa.md 建立本地快速索引
            self._index_qa_bank(context_dir)

        if external_context:
            self.system_instruction += f"\n\n【與會者背景與商業資料】\n{external_context}"

    def _index_qa_bank(self, context_dir):
        """解析 qa.md，將問題關鍵字與標準答案建立本地索引"""
        import re
        qa_path = os.path.join(context_dir, "qa.md")
        if not os.path.exists(qa_path):
            return

        # 定義常見停用詞，避免干擾匹配
        STOP_WORDS = {"how", "tell", "about", "your", "what", "where", "when", "with", "from", "into", "that", "this", "time", "have", "been"}

        try:
            with open(qa_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            sections = re.split(r'\n## ', content)
            for section in sections:
                lines = section.split('\n')
                if not lines: continue
                
                header = lines[0].strip()
                answer_match = re.search(r'\* \*\*標準答案：\*\* "(.*?)"', section, re.DOTALL)
                if not answer_match:
                    answer_match = re.search(r'\* \*\*標準答案：\*\* (.*)', section)
                
                if answer_match:
                    answer = answer_match.group(1).strip()
                    # 提取關鍵字並過濾掉停用詞
                    all_keywords = re.findall(r'[a-zA-Z]{3,}', header.lower())
                    filtered_keywords = {kw for kw in all_keywords if kw not in STOP_WORDS}
                    
                    if filtered_keywords:
                        self.qa_index.append({
                            "keywords": filtered_keywords,
                            "header": header,
                            "answer": answer
                        })
            print(f"✅ [Local Matcher] 已建立 {len(self.qa_index)} 條救命小抄索引。")
        except Exception as e:
            print(f"⚠️ [Local Matcher] 索引失敗: {e}")

    def get_local_hint(self, text):
        """零延遲匹配：檢查輸入文字是否命中本地題庫關鍵字"""
        if not text: return None
        text_lower = text.lower()
        best_match = None
        max_hits = 0
        
        for item in self.qa_index:
            # 計算命中數
            hits = sum(1 for kw in item["keywords"] if kw in text_lower)
            
            # 動態門檻邏輯：
            # 1. 如果關鍵字很少 (1-2個)，命中最少1個即中。
            # 2. 如果關鍵字較多，需命中 40% 以上的關鍵字。
            # 3. 如果命中了一個長度 >= 6 的長單字 (通常是專業術語)，權重加倍。
            long_word_hit = any(len(kw) >= 6 and kw in text_lower for kw in item["keywords"])
            effective_hits = hits + (1 if long_word_hit else 0)
            
            threshold = max(1, int(len(item["keywords"]) * 0.4))
            
            if effective_hits >= threshold and effective_hits > max_hits:
                max_hits = effective_hits
                best_match = item
        
        if best_match:
            return best_match["header"], best_match["answer"]
        return None

    def _get_optimal_model(self):
        try:
            available_models = [m.name.replace('models/', '') for m in self.client.models.list()]
            preferences = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
            for pref in preferences:
                if pref in available_models:
                    return pref
            return 'gemini-2.0-flash'
        except:
            return 'gemini-2.0-flash'

    def analyze_dialogue_sync(self, dialogue_text):
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
