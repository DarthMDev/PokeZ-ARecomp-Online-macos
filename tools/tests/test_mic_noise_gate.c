// Exercise gate decisions deterministically, independently of the VAD model.
#include "../../runtime/mic_noise.h"
#include "../../third_party/rnnoise/include/rnnoise.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float vad;
static float output_scale = 1.0f;
int rnnoise_get_frame_size(void) { return 480; }
DenoiseState *rnnoise_create(RNNModel *model) { (void)model; return (DenoiseState *)malloc(1); }
void rnnoise_destroy(DenoiseState *state) { free(state); }
float rnnoise_process_frame(DenoiseState *state, float *out, const float *in) {
    (void)state; for (int i = 0; i < 480; i++) out[i] = in[i] * output_scale; return vad;
}

static int frame(MicNoise *m, int level, float probability) {
    int16_t samples[480];
    for (int i = 0; i < 480; i++) samples[i] = (int16_t)(i & 1 ? level : -level);
    vad = probability;
    assert(mic_noise_process(m, samples, 480));
    return abs(samples[479]);
}

int main(void) {
    MicNoise *m = mic_noise_create(1); assert(m); mic_noise_set_strong(m, true);
    for (int i = 0; i < 200; i++) frame(m, 20, 0.1f);
    for (int i = 0; i < 40; i++) frame(m, 400, 0.95f);
    // A voice detector may be less confident for several seconds of speech.
    for (int i = 0; i < 300; i++) assert(frame(m, 400, 0.4f) > 300);
    // Brief pauses must not chop the next syllable.
    for (int i = 0; i < 30; i++) frame(m, 20, 0.0f);
    for (int i = 0; i < 40; i++) assert(frame(m, 400, 0.4f) > 300 || i == 0);
    // Sustained silence and low-level background still close the gate.
    int tail = 0;
    for (int i = 0; i < 200; i++) tail = frame(m, 20, 0.1f);
    assert(tail == 0);
    mic_noise_destroy(m);
    // Some microphones make the VAD report speech indefinitely on steady
    // background, even though RNNoise removes nearly all of that noise.
    m = mic_noise_create(1); assert(m); mic_noise_set_strong(m, true);
    output_scale = 0.05f;
    for (int i = 0; i < 800; i++) tail = frame(m, 200, 0.99f);
    assert(tail == 0);
    // Real speech can reopen the gate after the noise has been learned.
    output_scale = 1.0f;
    for (int i = 0; i < 100; i++) tail = frame(m, 1000, 0.95f);
    assert(tail > 900);
    mic_noise_destroy(m);
    puts("microphone gate sustained speech and silence passed");
    return 0;
}
