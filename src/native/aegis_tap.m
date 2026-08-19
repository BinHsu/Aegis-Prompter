// Aegis system-audio tap helper.
//
// Creates a global mono mixdown process tap and publishes it as an ordinary input device, then
// stays alive until it is signalled. It captures nothing itself: the Python side opens the
// published device through PortAudio like any microphone (V9), which is what keeps the capture
// pipeline identical for both tracks.
//
// Why a separate process rather than a Python extension:
//   - The tap and its aggregate device live exactly as long as this process. SIGTERM tears both
//     down, and so does a crash -- there is no path that leaves a phantom input device behind on
//     the operator's Mac.
//   - Creating a tap *is* capture (R25), so it must not happen at import, on a page load, or
//     anywhere except an explicit Start. A subprocess makes that boundary a process boundary.
//   - Tap capture triggers a kTCCServiceAudioCapture check attributed to the responsible process
//     -- the terminal or app that launched the tree, not this binary (V11).
//
// Build (Command Line Tools are sufficient; no Xcode -- V6):
//   clang -fobjc-arc -framework Foundation -framework CoreAudio \
//         -o src/native/aegis_tap src/native/aegis_tap.m
//
// Run:
//   src/native/aegis_tap                 # prints one JSON line, then blocks until signalled
//   src/native/aegis_tap --probe 4       # additionally reports peak level over 4 seconds
//
// The first stdout line is a single JSON object and is the contract with the caller. Everything
// else this program prints goes to stderr, so a caller may parse stdout without filtering.

#import <Foundation/Foundation.h>
#import <CoreAudio/CoreAudio.h>
#import <CoreAudio/AudioHardwareTapping.h>
#import <CoreAudio/CATapDescription.h>
#include <signal.h>
#include <stdatomic.h>
#include <unistd.h>

// macOS 14.2 is the floor, not 14.4 (V6). Declining per-app capture (R5) is what buys it: the
// bundleIDs and processRestoreEnabled members are the only ones that would demand 26.0 (V8).
#define AEGIS_TAP_DEVICE_NAME @"Aegis System Audio"
#define AEGIS_TAP_DEVICE_UID  @"com.aegis.prompter.systemaudio"

static atomic_bool g_should_exit = false;

static void handle_signal(int signum) {
    (void)signum;
    atomic_store(&g_should_exit, true);
}

static void log_err(NSString *format, ...) {
    va_list args;
    va_start(args, format);
    NSString *line = [[NSString alloc] initWithFormat:format arguments:args];
    va_end(args);
    fprintf(stderr, "%s\n", line.UTF8String);
}

/// Emit the one machine-readable line the caller parses, then flush -- the caller reads it while
/// this process is still running, so buffering it until exit would deadlock them both.
static void emit(NSDictionary *payload) {
    NSData *json = [NSJSONSerialization dataWithJSONObject:payload options:0 error:NULL];
    fwrite(json.bytes, 1, json.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

static void emit_failure(NSString *stage, OSStatus status, NSString *detail) {
    emit(@{@"ok": @NO, @"stage": stage, @"status": @(status), @"detail": detail ?: @""});
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        double probe_seconds = 0.0;
        for (int i = 1; i < argc; i++) {
            if (strcmp(argv[i], "--probe") == 0 && i + 1 < argc) {
                probe_seconds = atof(argv[++i]);
            }
        }

        // ---- The tap itself -------------------------------------------------------------
        //
        // `initMonoGlobalTapButExcludeProcesses:` with an empty exclusion list is the whole of
        // R1 and R5: every process that outputs audio is included, and nothing has to know or be
        // told which application the meeting is running in. It takes no device UID -- a global
        // tap is defined process-wise, not device-wise, which is why switching the operator's
        // output to a headset is not expected to affect it.
        //
        // Mono because the pipeline is mono end to end: webrtcvad and every ASR candidate consume
        // one channel, so mixing down here rather than later avoids carrying a channel that is
        // discarded anyway.
        CATapDescription *description =
            [[CATapDescription alloc] initMonoGlobalTapButExcludeProcesses:@[]];
        description.name = @"Aegis Prompter";
        // CATapUnmuted keeps the audio audible to the operator (V10). This is what removes
        // BlackHole's Multi-Output Device requirement (R6): tapping is a read, and the operator
        // keeps hearing the meeting through whatever device they already chose.
        description.muteBehavior = CATapUnmuted;
        description.privateTap = NO;

        AudioObjectID tap_id = kAudioObjectUnknown;
        OSStatus status = AudioHardwareCreateProcessTap(description, &tap_id);
        if (status != noErr || tap_id == kAudioObjectUnknown) {
            emit_failure(@"create-tap", status,
                         @"AudioHardwareCreateProcessTap failed. On a first run this is usually "
                         @"the audio-capture permission (V11): grant it to the application that "
                         @"launched this process, not to this binary.");
            return 1;
        }

        // The tap's own UID is what the aggregate device refers to. Read it back rather than
        // reusing description.UUID -- they are not required to be the same string, and guessing
        // produces an aggregate device that builds successfully and carries no audio.
        CFStringRef tap_uid_ref = NULL;
        UInt32 size = sizeof(tap_uid_ref);
        AudioObjectPropertyAddress uid_address = {
            kAudioTapPropertyUID, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain
        };
        status = AudioObjectGetPropertyData(tap_id, &uid_address, 0, NULL, &size, &tap_uid_ref);
        if (status != noErr || tap_uid_ref == NULL) {
            emit_failure(@"read-tap-uid", status, @"kAudioTapPropertyUID unavailable");
            AudioHardwareDestroyProcessTap(tap_id);
            return 1;
        }
        NSString *tap_uid = (__bridge_transfer NSString *)tap_uid_ref;

        AudioStreamBasicDescription format = {0};
        size = sizeof(format);
        AudioObjectPropertyAddress format_address = {
            kAudioTapPropertyFormat, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain
        };
        // Not fatal: the format is reported for the caller's benefit (V12 is about who resamples
        // it), and an aggregate device that carries audio is still useful without it.
        OSStatus format_status =
            AudioObjectGetPropertyData(tap_id, &format_address, 0, NULL, &size, &format);

        // ---- Publish it as an input device ----------------------------------------------
        //
        // Non-private on purpose (V9): a private aggregate is visible only to the process that
        // created it, and the whole point of this helper is that a *different* process -- Python,
        // through PortAudio -- opens it as an ordinary microphone. That keeps one capture path
        // for both tracks instead of a second, native one for system audio.
        NSDictionary *aggregate = @{
            @kAudioAggregateDeviceNameKey: AEGIS_TAP_DEVICE_NAME,
            @kAudioAggregateDeviceUIDKey: AEGIS_TAP_DEVICE_UID,
            @kAudioAggregateDeviceIsPrivateKey: @NO,
            @kAudioAggregateDeviceIsStackedKey: @NO,
            @kAudioAggregateDeviceTapAutoStartKey: @YES,
            @kAudioAggregateDeviceTapListKey: @[@{
                @kAudioSubTapUIDKey: tap_uid,
                @kAudioSubTapDriftCompensationKey: @NO,
            }],
        };

        AudioObjectID device_id = kAudioObjectUnknown;
        status = AudioHardwareCreateAggregateDevice((__bridge CFDictionaryRef)aggregate, &device_id);
        if (status != noErr || device_id == kAudioObjectUnknown) {
            emit_failure(@"create-aggregate", status,
                         @"AudioHardwareCreateAggregateDevice failed; a stale device with the "
                         @"same UID from a killed run is the usual cause.");
            AudioHardwareDestroyProcessTap(tap_id);
            return 1;
        }

        emit(@{
            @"ok": @YES,
            @"device_name": AEGIS_TAP_DEVICE_NAME,
            @"device_uid": AEGIS_TAP_DEVICE_UID,
            @"tap_uid": tap_uid,
            @"sample_rate": format_status == noErr ? @(format.mSampleRate) : [NSNull null],
            @"channels": format_status == noErr ? @(format.mChannelsPerFrame) : [NSNull null],
            @"pid": @(getpid()),
        });
        log_err(@"[aegis_tap] published '%@' (uid %@); waiting for SIGTERM",
                AEGIS_TAP_DEVICE_NAME, AEGIS_TAP_DEVICE_UID);

        // ---- Optional self-probe --------------------------------------------------------
        //
        // Exists so the tap can be verified without the Python stack -- specifically so "does
        // this still capture when output is a Bluetooth headset" is one command rather than a
        // dependency chain. Reports peak amplitude, because the question is only ever "is there
        // signal or is there silence".
        if (probe_seconds > 0.0) {
            AudioDeviceIOProcID proc_id = NULL;
            __block float peak = 0.0f;
            __block UInt64 frames = 0;
            status = AudioDeviceCreateIOProcIDWithBlock(
                &proc_id, device_id, NULL,
                ^(const AudioTimeStamp *now, const AudioBufferList *in, const AudioTimeStamp *inTime,
                  AudioBufferList *out, const AudioTimeStamp *outTime) {
                    (void)now; (void)inTime; (void)out; (void)outTime;
                    for (UInt32 b = 0; b < in->mNumberBuffers; b++) {
                        const float *samples = (const float *)in->mBuffers[b].mData;
                        UInt32 count = in->mBuffers[b].mDataByteSize / sizeof(float);
                        for (UInt32 i = 0; i < count; i++) {
                            float magnitude = fabsf(samples[i]);
                            if (magnitude > peak) peak = magnitude;
                        }
                        frames += count;
                    }
                });
            if (status == noErr) {
                AudioDeviceStart(device_id, proc_id);
                usleep((useconds_t)(probe_seconds * 1e6));
                AudioDeviceStop(device_id, proc_id);
                AudioDeviceDestroyIOProcID(device_id, proc_id);
                emit(@{@"probe": @YES, @"seconds": @(probe_seconds),
                       @"frames": @(frames), @"peak": @(peak)});
            } else {
                emit(@{@"probe": @NO, @"stage": @"create-ioproc", @"status": @(status)});
            }
        }

        // ---- Live until signalled -------------------------------------------------------
        signal(SIGTERM, handle_signal);
        signal(SIGINT, handle_signal);
        while (!atomic_load(&g_should_exit)) {
            usleep(100000);
        }

        // Destroy the aggregate first: it references the tap, and tearing the tap out from under
        // it is what leaves an input device on the operator's Mac that plays nothing and cannot
        // be removed without a reboot.
        AudioHardwareDestroyAggregateDevice(device_id);
        AudioHardwareDestroyProcessTap(tap_id);
        log_err(@"[aegis_tap] torn down cleanly");
        return 0;
    }
}
