import sounddevice as sd
import numpy as np
import time

def test_audio_input(device_name, seconds=2):
    print(f"\n🎤 測試設備: {device_name} ({seconds}秒)...")
    
    # 搜尋設備編號
    devices = sd.query_devices()
    target_idx = -1
    for i, dev in enumerate(devices):
        if device_name.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
            target_idx = i
            break
    
    if target_idx == -1:
        print(f"❌ 找不到設備: {device_name}")
        return

    # 嘗試打開 InputStream 並讀取數據
    try:
        recording = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, device=target_idx)
        print("   [錄製中... 請對著麥克風講話]")
        sd.wait()
        
        # 計算 RMS 音量
        rms = np.sqrt(np.mean(recording**2))
        print(f"   📊 平均震幅 (RMS): {rms:.6f}")
        
        if rms < 0.0001:
            print("   ⚠️ 警告：音量極低甚至為 0。請檢查 macOS 系統設定中的「麥克風權限」！")
        else:
            print("   ✅ 成功偵測到音頻訊號！")
            
    except Exception as e:
        print(f"   ❌ 錄製失敗: {e}")

def list_devices():
    print("\n--- 系統偵測到的音訊設備清單 ---")
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        print(f"編號 {i}: {dev['name']} (輸入頻道: {dev['max_input_channels']})")

if __name__ == "__main__":
    list_devices()
    print("\n" + "="*50)
    print("🚀 啟動硬體連通性檢測...")
    test_audio_input("MacBook Air Microphone")
    test_audio_input("BlackHole")
    print("="*50)
