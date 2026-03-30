import sounddevice as sd
import numpy as np
import time

# 快取當前音量大小的字典
rms_data = {"mic": 0.0, "bh": 0.0}

def mic_callback(indata, frames, time_info, status):
    if status: print(f"Mic Status: {status}")
    rms_data["mic"] = np.sqrt(np.mean(indata**2))

def bh_callback(indata, frames, time_info, status):
    if status: print(f"BH Status: {status}")
    rms_data["bh"] = np.sqrt(np.mean(indata**2))

def find_device(keyword):
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if keyword.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
            return i
    return None

def main():
    print("🎤 [Staff Officer] 雙音軌隔離健檢程式啟動中...\n")
    
    mic_idx = find_device("MacBook") # 通常 M4 會叫 MacBook Air Microphone
    bh_idx = find_device("BlackHole")
    
    if mic_idx is None:
        print("⚠️ 找不到名稱含有 'MacBook' 的裝置。將使用系統預設麥克風。")
        mic_idx = sd.default.device[0]
        
    if bh_idx is None:
        print("❌ 找不到 'BlackHole' 音效卡。請確認是否已透過 brew install --cask blackhole-2ch 安裝。")
        print("\n⚠️ 系統目前的輸入裝置清單：")
        print(sd.query_devices())
        return
        
    print(f"🎙️ 麥克風鎖定: [{mic_idx}] {sd.query_devices(mic_idx)['name']}")
    print(f"🎧 混音器鎖定: [{bh_idx}] {sd.query_devices(bh_idx)['name']}\n")
    
    try:
        # 強制只吃單聲道以節省運算並統一格式
        stream_mic = sd.InputStream(device=mic_idx, callback=mic_callback, channels=1, blocksize=4000)
        stream_bh = sd.InputStream(device=bh_idx, callback=bh_callback, channels=1, blocksize=4000)
        
        with stream_mic, stream_bh:
            print("🚀 開始即時監聽音量。")
            print("👉 請試著對您的麥克風講話，並同時在電腦播放 Youtube，觀察兩條音軌是否被完美隔離。")
            print("🔴 按下 [Ctrl+C] 退出。\n")
            
            print(f"{'🎙️ MacBook Mic (自己的聲音)':<30} | {'🎧 BlackHole (面試官/筆電聲音)':<30}")
            print("-" * 65)
            
            while True:
                # 定義最高條為 40 格，乘上一個靈敏度係數 (視麥克風硬體不同可能需調整)
                mic_vol = min(int(rms_data["mic"] * 1000), 30)
                bh_vol = min(int(rms_data["bh"] * 1000), 30)
                
                mic_bar = "█" * mic_vol
                bh_bar = "🔥" * bh_vol
                
                # \r 回車覆蓋同一行
                print(f"\r{mic_bar:<30} | {bh_bar:<30}", end='', flush=True)
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\n\n✅ 健檢完成，程式已終止。")
    except Exception as e:
        print(f"\n❌ 無法開啟音訊串流，錯誤: {e}")

if __name__ == "__main__":
    main()
