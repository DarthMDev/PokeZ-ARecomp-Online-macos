#include "../../runtime/mic_noise.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    enum { FRAMES = 480 * 24, CHANNELS = 2, N = FRAMES * CHANNELS };
    int16_t *whole = malloc(N * sizeof *whole), *split = malloc(N * sizeof *split);
    assert(whole && split);
    uint32_t rng = 12345;
    for (int i = 0; i < N; i++) { rng = rng * 1664525u + 1013904223u; whole[i] = (int16_t)((int)(rng >> 20) - 2048); }
    memcpy(split, whole, N * sizeof *split);
    MicNoise *a = mic_noise_create(CHANNELS), *b = mic_noise_create(CHANNELS);
    assert(a && b && !mic_noise_create(0) && !mic_noise_create(3));
    assert(!mic_noise_process(a, whole, 1)); // reject a partial stereo frame without changing state
    assert(mic_noise_process(a, whole, N));
    for (int off = 0; off < N;) {
        int n = 62; if (n > N - off) n = N - off;
        assert(mic_noise_process(b, split + off, n)); off += n;
    }
    assert(!memcmp(whole, split, N * sizeof *whole));
    for (int i = 0; i < 480 * CHANNELS; i++) assert(whole[i] == 0); // one initial 10 ms frame
    int nonzero = 0; for (int i = 480 * CHANNELS; i < N; i++) nonzero |= whole[i] != 0;
    assert(nonzero);
    mic_noise_destroy(a); mic_noise_destroy(b); free(whole); free(split);
    // With identical steady background noise, Strong should reduce the
    // residual between-speech level more than Standard.
    enum { LONG_N = 480 * 160 };
    int16_t *standard = malloc(LONG_N * sizeof *standard), *strong = malloc(LONG_N * sizeof *strong);
    assert(standard && strong);
    for (int i = 0; i < LONG_N; i++) { rng = rng * 1664525u + 1013904223u; standard[i] = (int16_t)((int)(rng >> 20) - 2048); }
    memcpy(strong, standard, LONG_N * sizeof *strong);
    a = mic_noise_create(1); b = mic_noise_create(1); assert(a && b); mic_noise_set_strong(b, true);
    assert(mic_noise_process(a, standard, LONG_N) && mic_noise_process(b, strong, LONG_N));
    double normal_energy = 0, strong_energy = 0;
    for (int i = LONG_N / 2; i < LONG_N; i++) { normal_energy += (double)standard[i] * standard[i]; strong_energy += (double)strong[i] * strong[i]; }
    assert(normal_energy > 0 && strong_energy < normal_energy * 0.5);
    int tail_nonzero = 0;
    for (int i = LONG_N - 480; i < LONG_N; i++) tail_nonzero |= strong[i] != 0;
    assert(!tail_nonzero); // stable background noise fades fully to silence
    mic_noise_destroy(a); mic_noise_destroy(b); free(standard); free(strong);
    puts("microphone noise filter continuity and strong mode passed");
    return 0;
}
