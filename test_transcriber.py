import time
import sys
import os

# 將 src 資料夾加入 Python 尋找路徑中
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from dialogue_buffer import DialogueBuffer
from transcriber import Transcriber

def main():
    buffer = DialogueBuffer(max_history=10)
    print("🚀 啟動 Transcriber 與 M4 NPU 實機測試...")
    
    # 建立一個測試用的轉錄大腦 (device_idx=None 代表使用系統目前的預設輸入對著麥克風)
    t = Transcriber(device_idx=None, role="測試者 (Bin)", buffer_instance=buffer)
    t.start()
    
    try:
        print("\n👉 請隨意對著麥克風講幾句話測試。您可以試著停頓或是連珠炮地說。")
        print("   (因為要等您講完才會丟給 Whisper，請記得講完後停頓 0.6 秒觀察終端機)")
        print("🔴 測試將在 20 秒後自動結束，或者您可以隨時按 [Ctrl+C] 提早結束。\n")
        
        for i in range(20, 0, -1):
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n使用者提早中斷測試。")
    finally:
        print("\n🛑 正在停止收音引擎並釋放資源...")
        t.stop()
        
        print("\n================ [防打斷對話緩衝區] 收集結果 ================")
        result = buffer.get_formatted_dialogue()
        if not result:
            print("(完全沒有收到有效的人類語音)")
        else:
            print(result)
        print("=========================================================")

if __name__ == "__main__":
    main()
