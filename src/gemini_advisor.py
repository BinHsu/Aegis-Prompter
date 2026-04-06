import os
import threading
import glob
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

class GeminiAdvisor:
    def __init__(self, context_dir=None):
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
        # ⚡️ [產品級優化]：載入上下文與動態路徑掛載
        # ==========================================================
        if context_dir is None:
            context_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context")
        
        external_context = ""
        self.qa_index = []
        
        # 1. 讀取本機 QA 作為 Local Matcher
        self._index_qa_bank(context_dir)
        
        # 2. 收集所有要讀取的目錄路徑
        directories_to_scan = [context_dir]
        knowledge_conf = os.path.join(context_dir, "knowledge.md")
        if os.path.exists(knowledge_conf):
            with open(knowledge_conf, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if os.path.isdir(line):
                            directories_to_scan.append(line)
                        else:
                            print(f"⚠️ 找不到設定的知識庫目錄: {line}")
        
        # 3. 讀取所有目錄下的 MD 與 TXT
        scanned_files = set()
        for d in directories_to_scan:
            for filepath in glob.glob(os.path.join(d, "**/*.*"), recursive=True):
                if filepath.endswith(('.md', '.txt')) and filepath not in scanned_files:
                    scanned_files.add(filepath)
                    # 避免把自己 knowledge.md 讀進去 (無意義)
                    if os.path.basename(filepath).lower() == "knowledge.md":
                        continue
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            filename = os.path.basename(filepath)
                            # 附上檔名與資料夾作為提示線索
                            external_context += f"\n--- 檔案參考: {filename} ({d}) ---\n{content}\n"
                    except Exception as e:
                        pass
        
        self.cached_content_name = None
        
        if external_context:
            print(f"📚 成功載入 {len(scanned_files)} 個外部知識檔案，總字數: {len(external_context)}")
            
            # --- 快取嘗試與降級機制 ---
            try:
                # 綁定支援快取的特定模型
                cache_model_target = "gemini-1.5-flash-002" 
                print(f"🌀 嘗試建立 Context Cache，保存時限 2 小時...")
                cache = self.client.caches.create(
                    model=cache_model_target,
                    config=types.CreateCachedContentConfig(
                        contents=external_context,
                        system_instruction=self.system_instruction,
                        ttl="7200s", # 2小時
                        display_name="staff_officer_knowledge"
                    )
                )
                self.cached_content_name = cache.name
                self.model_name = cache_model_target # 強制切換為快取對應模型
                print(f"✅ 成功建立快取！Cache ID: {self.cached_content_name}")
            except Exception as e:
                # 依據使用者要求：如果快取建立失敗 (例如字數不到 32000 tokens 或 API 問題)，直接放棄掛載外部知識，避免拖慢面試效能與產生高額 Token 費用
                print(f"⚠️ 無法建立快取 (可能金額度不足或連線問題)。為確保面試流暢，已主動捨棄外部知識庫。提示: {e}")

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
            if self.cached_content_name:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=dialogue_text,
                    config=types.GenerateContentConfig(
                        cached_content=self.cached_content_name,
                        temperature=0.3
                    )
                )
            else:
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
