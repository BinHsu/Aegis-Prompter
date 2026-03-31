import sounddevice as sd

def list_devices():
    print("\n--- 可用的音訊設備 (sounddevice) ---")
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        print(f"編號 {i}: {dev['name']} (輸入頻道: {dev['max_input_channels']})")

if __name__ == "__main__":
    list_devices()
