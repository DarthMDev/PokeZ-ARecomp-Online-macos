// Microphone input for nn::audio::detail::IAudioIn. Audio remains paused until Start.
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <SDL3/SDL.h>
#include "../hle.h"
#include "../ipc.h"
#include "../settings.h"
#include "../mic_noise.h"

enum { INPUT_QUEUE = 64, MAX_INPUT_BYTES = 1024 * 1024 };
typedef struct { uint64_t tag, data; uint32_t size; } InputBuffer;
typedef struct {
    uint32_t rate, channels, state, ev_r, ev_w;
    float gain, applied_gain;
    SDL_AudioStream *stream;
    KEvent *event;
    pthread_mutex_t lock;
    pthread_t thread;
    atomic_bool quit;
    InputBuffer queued[INPUT_QUEUE];
    uint64_t released[INPUT_QUEUE];
    unsigned count, released_count, completed;
    bool logged_append, noise_unavailable;
    MicNoise *noise;
} AudioIn;

static AudioIn *inputs[8];
static pthread_mutex_t inputs_lock = PTHREAD_MUTEX_INITIALIZER;
static _Atomic float input_master_gain = 1.0f;
static _Atomic bool input_noise_enabled, input_noise_strong;
void audio_input_set_master_gain(float gain) { atomic_store(&input_master_gain, gain); }
void audio_input_set_noise_suppression(bool enabled) { atomic_store(&input_noise_enabled, enabled); }
void audio_input_set_noise_strong(bool strong) { atomic_store(&input_noise_strong, strong); }

// Copies device names for the settings menu; does not open a microphone.
int audio_input_device_names(char names[][256], int max) {
    if (!(SDL_WasInit(SDL_INIT_AUDIO) & SDL_INIT_AUDIO) && !SDL_InitSubSystem(SDL_INIT_AUDIO)) return 0;
    int count = 0, written = 0;
    SDL_AudioDeviceID *devices = SDL_GetAudioRecordingDevices(&count);
    for (int i = 0; devices && i < count && written < max; i++) {
        const char *name = SDL_GetAudioDeviceName(devices[i]);
        if (name && *name) snprintf(names[written++], 256, "%s", name);
    }
    SDL_free(devices);
    return written;
}

static SDL_AudioDeviceID input_device(void) {
    if (!g_settings.mic_device[0]) return SDL_AUDIO_DEVICE_DEFAULT_RECORDING;
    int count = 0;
    SDL_AudioDeviceID *devices = SDL_GetAudioRecordingDevices(&count), selected = SDL_AUDIO_DEVICE_DEFAULT_RECORDING;
    bool found = false;
    for (int i = 0; devices && i < count; i++) {
        const char *name = SDL_GetAudioDeviceName(devices[i]);
        if (name && !strcmp(name, g_settings.mic_device)) { selected = devices[i]; found = true; break; }
    }
    SDL_free(devices);
    if (!found) LOG("[audin] selected microphone unavailable; using system default\n");
    return selected;
}

static void *input_thread(void *arg) {
    AudioIn *a = arg;
    while (!atomic_load(&a->quit)) {
        pthread_mutex_lock(&a->lock);
        float combined_gain = a->gain * atomic_load(&input_master_gain);
        if (!(combined_gain >= 0.0f && combined_gain <= 192.0f)) combined_gain = 1.0f;
        bool noise_on = atomic_load(&input_noise_enabled);
        if (!noise_on) { if (a->noise) mic_noise_destroy(a->noise); a->noise = NULL; a->noise_unavailable = false; }
        if (!a->state && a->count && a->released_count < INPUT_QUEUE) {
            InputBuffer b = a->queued[0];
            bool valid_frames = !(b.size % (sizeof(int16_t) * a->channels));
            if (noise_on && valid_frames && !a->noise && !a->noise_unavailable) {
                a->noise = a->rate == 48000 ? mic_noise_create(a->channels) : NULL;
                if (!a->noise) { LOG("[audin] noise suppression unavailable for this input format\n"); a->noise_unavailable = true; }
                else LOG("[audin] local noise suppression enabled\n");
            }
            // Keep large boosts from turning background hiss into apparent speech.
            // Apply the rest only after filtering; preserve the total requested gain.
            bool filtering = noise_on && a->noise && valid_frames;
            float pre_gain = filtering && combined_gain > 6.0f ? 6.0f : combined_gain;
            float post_gain = pre_gain > 0.0f ? combined_gain / pre_gain : 1.0f;
            if (a->applied_gain != pre_gain) { SDL_SetAudioStreamGain(a->stream, pre_gain); a->applied_gain = pre_gain; }
            int available = SDL_GetAudioStreamAvailable(a->stream);
            if (available >= (int)b.size || available < 0) {
                int n = available < 0 ? 0 : SDL_GetAudioStreamData(a->stream, (void *)(uintptr_t)b.data, (int)b.size);
                if (n < 0) n = 0;
                if ((uint32_t)n < b.size) memset((void *)(uintptr_t)(b.data + n), 0, b.size - (uint32_t)n);
                if (filtering) {
                    mic_noise_set_strong(a->noise, atomic_load(&input_noise_strong));
                    if (!mic_noise_process(a->noise, (int16_t *)(uintptr_t)b.data, b.size / 2))
                        LOG("[audin] noise suppression skipped an incomplete sample frame\n");
                    if (post_gain != 1.0f) {
                        int16_t *samples = (int16_t *)(uintptr_t)b.data;
                        for (uint32_t i = 0; i < b.size / 2; i++) {
                            float value = samples[i] * post_gain;
                            if (value > 32767.0f) value = 32767.0f;
                            if (value < -32768.0f) value = -32768.0f;
                            samples[i] = (int16_t)value;
                        }
                    }
                }
                if (!a->completed++) {
                    const int16_t *samples = (const int16_t *)(uintptr_t)b.data;
                    int peak = 0;
                    for (uint32_t i = 0; i < b.size / 2; i++) {
                        int value = samples[i]; if (value < 0) value = -value;
                        if (value > peak) peak = value;
                    }
                    LOG("[audin] first buffer: %d/%u bytes captured, peak %d/32768\n", n, b.size, peak);
                }
                a->released[a->released_count++] = b.tag;
                memmove(a->queued, a->queued + 1, --a->count * sizeof(a->queued[0]));
                pthread_mutex_lock(&g_klock);
                kernel_signal(a->event);
                pthread_mutex_unlock(&g_klock);
            }
        }
        pthread_mutex_unlock(&a->lock);
        struct timespec delay = {0, 2000000};
        nanosleep(&delay, NULL);
    }
    return NULL;
}

static void input_free(AudioIn *a) {
    atomic_store(&a->quit, true);
    pthread_join(a->thread, NULL);
    SDL_DestroyAudioStream(a->stream);
    mic_noise_destroy(a->noise);
    pthread_mutex_destroy(&a->lock);
    free(a);
}

static void input_close(Service *s) {
    AudioIn *a = s->state;
    bool owned = false;
    pthread_mutex_lock(&inputs_lock);
    for (int i = 0; i < 8; i++) if (inputs[i] == a) { inputs[i] = NULL; owned = true; }
    pthread_mutex_unlock(&inputs_lock);
    if (owned) { s->state = NULL; input_free(a); LOG("[audin] closed\n"); }
}

RT_ON_RESET(audio_input_reset) {
    pthread_mutex_lock(&inputs_lock);
    for (int i = 0; i < 8; i++) if (inputs[i]) { input_free(inputs[i]); inputs[i] = NULL; }
    pthread_mutex_unlock(&inputs_lock);
}

static void audio_input(Service *s, IpcReq *req, IpcResp *resp) {
    AudioIn *a = s->state;
    if (!a) { resp->result = MAKE_RESULT(153, 1); return; }
    switch (req->cmd) {
    case 0: pthread_mutex_lock(&a->lock); OUT(uint32_t, 0) = a->state; pthread_mutex_unlock(&a->lock); resp_size(resp, 4); break;
    case 1:
        pthread_mutex_lock(&a->lock);
        SDL_ClearAudioStream(a->stream);
        if (SDL_ResumeAudioStreamDevice(a->stream)) a->state = 0;
        else resp->result = MAKE_RESULT(153, 1);
        pthread_mutex_unlock(&a->lock);
        LOG("[audin] capture %s\n", resp->result ? "failed to start" : "started");
        break;
    case 2:
        pthread_mutex_lock(&a->lock); a->state = 1; SDL_PauseAudioStreamDevice(a->stream); SDL_ClearAudioStream(a->stream); pthread_mutex_unlock(&a->lock);
        LOG("[audin] capture stopped\n"); break;
    case 3: case 8: {
        IpcBuf *b = in_buf(req, 0);
        if (!b || b->size < 0x28 || !b->addr || req->data_size < 8) { resp->result = MAKE_RESULT(153, 1); break; }
        const uint64_t *v = (const uint64_t *)(uintptr_t)b->addr;
        uint64_t capacity = v[2], offset = v[4];
        uint64_t length = v[3] ? v[3] : (offset <= capacity ? capacity - offset : 0);
        if (!v[1] || offset > capacity || length > capacity - offset || !length || length > MAX_INPUT_BYTES || v[1] + offset < v[1]) { resp->result = MAKE_RESULT(153, 1); break; }
        pthread_mutex_lock(&a->lock);
        if (a->count == INPUT_QUEUE) resp->result = MAKE_RESULT(153, 1);
        else {
            a->queued[a->count++] = (InputBuffer){IN(uint64_t, 0), v[1] + offset, (uint32_t)length};
            if (!a->logged_append) { LOG("[audin] queued first %u-byte buffer\n", (unsigned)length); a->logged_append = true; }
        }
        pthread_mutex_unlock(&a->lock);
        break;
    }
    case 4: resp->copy_handles[resp->ncopy++] = a->ev_r; break;
    case 5: case 9: {
        IpcBuf *b = out_buf(req, 0);
        pthread_mutex_lock(&a->lock);
        unsigned n = a->released_count, max = b ? (unsigned)(b->size / 8) : 0;
        if (n > max) n = max;
        if (n) memcpy((void *)(uintptr_t)b->addr, a->released, n * sizeof(uint64_t));
        memmove(a->released, a->released + n, (a->released_count - n) * sizeof(uint64_t));
        a->released_count -= n;
        pthread_mutex_unlock(&a->lock);
        OUT(uint32_t, 0) = n; resp_size(resp, 4); break;
    }
    case 6: {
        bool found = false; uint64_t tag = req->data_size >= 8 ? IN(uint64_t, 0) : 0;
        pthread_mutex_lock(&a->lock);
        for (unsigned i = 0; i < a->count; i++) found |= a->queued[i].tag == tag;
        pthread_mutex_unlock(&a->lock);
        OUT(uint8_t, 0) = found; resp_size(resp, 1); break;
    }
    case 11: pthread_mutex_lock(&a->lock); OUT(uint32_t, 0) = a->count; pthread_mutex_unlock(&a->lock); resp_size(resp, 4); break;
    case 12: if (req->data_size >= 4) { pthread_mutex_lock(&a->lock); a->gain = IN(float, 0); pthread_mutex_unlock(&a->lock); } break;
    case 13: pthread_mutex_lock(&a->lock); OUT(float, 0) = a->gain; pthread_mutex_unlock(&a->lock); resp_size(resp, 4); break;
    case 14: {
        pthread_mutex_lock(&a->lock);
        unsigned n = 0;
        while (a->count && a->released_count < INPUT_QUEUE) {
            a->released[a->released_count++] = a->queued[0].tag;
            memmove(a->queued, a->queued + 1, --a->count * sizeof(a->queued[0])); n++;
        }
        if (n) { pthread_mutex_lock(&g_klock); kernel_signal(a->event); pthread_mutex_unlock(&g_klock); }
        pthread_mutex_unlock(&a->lock);
        OUT(uint8_t, 0) = n != 0; resp_size(resp, 1); break;
    }
    default: LOG("[audin] unsupported IAudioIn cmd %u\n", req->cmd); resp->result = MAKE_RESULT(153, 1);
    }
}

SERVICE("audin:u", audin_u) {
    (void)s;
    switch (req->cmd) {
    case 0: case 2: case 4: {
        IpcBuf *b = out_buf(req, 0);
        if (b && b->size) { memset((void *)(uintptr_t)b->addr, 0, b->size); strncpy((char *)(uintptr_t)b->addr, "BuiltInHeadset", b->size - 1); }
        OUT(uint32_t, 0) = 1; resp_size(resp, 4); break;
    }
    case 1: case 3: case 5: {
        // Command 5 prefixes the ordinary input configuration with a u64 protocol.
        const unsigned param_offset = req->cmd == 5 ? 8 : 0;
        if (req->data_size < param_offset + 8 || !SDL_InitSubSystem(SDL_INIT_AUDIO)) { resp->result = MAKE_RESULT(153, 1); break; }
        AudioIn *a = calloc(1, sizeof *a);
        if (!a) { resp->result = MAKE_RESULT(153, 1); break; }
        a->rate = IN(uint32_t, param_offset); if (a->rate < 8000 || a->rate > 192000) a->rate = 48000;
        a->channels = IN(uint32_t, param_offset + 4) & 0xffff; if (a->channels != 1 && a->channels != 2) a->channels = 2;
        a->state = 1; a->gain = 1.0f; a->applied_gain = -1.0f;
        atomic_store(&input_master_gain, g_settings.mic_gain);
        atomic_store(&input_noise_enabled, g_settings.mic_noise_suppression);
        atomic_store(&input_noise_strong, g_settings.mic_noise_strong);
        SDL_AudioDeviceID selected = input_device();
        const char *device_name = SDL_GetAudioDeviceName(selected);
        LOG("[audin] recording device: %s\n", device_name ? device_name : "system default");
        SDL_AudioSpec spec = {SDL_AUDIO_S16, (int)a->channels, (int)a->rate};
        a->stream = SDL_OpenAudioDeviceStream(selected, &spec, NULL, NULL);
        if (!a->stream) { LOG("[audin] microphone unavailable: %s\n", SDL_GetError()); free(a); resp->result = MAKE_RESULT(153, 1); break; }
        pthread_mutex_init(&a->lock, NULL);
        a->event = kernel_create_event_pair(&a->ev_w, &a->ev_r);
        pthread_mutex_lock(&inputs_lock);
        int slot = 0; while (slot < 8 && inputs[slot]) slot++;
        if (slot == 8 || pthread_create(&a->thread, NULL, input_thread, a)) {
            pthread_mutex_unlock(&inputs_lock); SDL_DestroyAudioStream(a->stream); pthread_mutex_destroy(&a->lock); free(a); resp->result = MAKE_RESULT(153, 1); break;
        }
        inputs[slot] = a; pthread_mutex_unlock(&inputs_lock);
        IpcBuf *b = out_buf(req, 0);
        if (b && b->size) { memset((void *)(uintptr_t)b->addr, 0, b->size); strncpy((char *)(uintptr_t)b->addr, "BuiltInHeadset", b->size - 1); }
        OUT(uint32_t, 0) = a->rate; OUT(uint32_t, 4) = a->channels; OUT(uint32_t, 8) = 2; OUT(uint32_t, 12) = 1; resp_size(resp, 16);
        Service *svc = service_new("IAudioIn", audio_input, a); svc->on_close = input_close; ipc_return_object(resp, svc);
        LOG("[audin] microphone opened %u Hz, %u ch (paused)\n", a->rate, a->channels); break;
    }
    default: LOG("[audin] unsupported manager cmd %u\n", req->cmd); resp->result = MAKE_RESULT(153, 1);
    }
}
