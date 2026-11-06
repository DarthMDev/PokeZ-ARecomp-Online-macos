// Local RNNoise microphone filtering; one frame (10 ms) of buffering.
#include "mic_noise.h"
#include "../third_party/rnnoise/include/rnnoise.h"
#include <stdlib.h>
#include <math.h>

enum { NOISE_FRAME = 480 };
struct MicNoise {
    DenoiseState *state[2];
    float input[2][NOISE_FRAME], output[2][NOISE_FRAME];
    unsigned channels, position, speech_hold;
    float gate;
    double frame_energy;
    float noise_floor, level_smooth;
    bool ready, strong;
};

MicNoise *mic_noise_create(unsigned channels) {
    if ((channels != 1 && channels != 2) || rnnoise_get_frame_size() != NOISE_FRAME) return NULL;
    MicNoise *m = calloc(1, sizeof *m);
    if (!m) return NULL;
    m->channels = channels;
    m->gate = 1.0f;
    m->noise_floor = 30.0f;
    for (unsigned c = 0; c < channels; c++) {
        m->state[c] = rnnoise_create(NULL);
        if (!m->state[c]) { mic_noise_destroy(m); return NULL; }
    }
    return m;
}

void mic_noise_destroy(MicNoise *m) {
    if (!m) return;
    for (unsigned c = 0; c < m->channels; c++) if (m->state[c]) rnnoise_destroy(m->state[c]);
    free(m);
}

void mic_noise_set_strong(MicNoise *m, bool strong) { if (m) m->strong = strong; }

bool mic_noise_process(MicNoise *m, int16_t *samples, size_t count) {
    if (!m || !samples || count % m->channels) return false;
    for (size_t i = 0; i < count; i += m->channels) {
        for (unsigned c = 0; c < m->channels; c++) {
            float x = samples[i + c];
            float y = m->ready ? m->output[c][m->position] : 0.0f;
            m->input[c][m->position] = x;
            m->frame_energy += x * x;
            if (y > 32767.0f) y = 32767.0f;
            if (y < -32768.0f) y = -32768.0f;
            samples[i + c] = (int16_t)y;
        }
        if (++m->position == NOISE_FRAME) {
            float speech = 0.0f;
            for (unsigned c = 0; c < m->channels; c++) {
                float probability = rnnoise_process_frame(m->state[c], m->output[c], m->input[c]);
                if (probability > speech) speech = probability;
            }
            float level = (float)sqrt(m->frame_energy / (NOISE_FRAME * m->channels));
            m->frame_energy = 0;
            m->level_smooth += 0.1f * (level - m->level_smooth);
            // Strong mode fades down residual noise between speech, with a hold
            // and gradual release so short pauses do not chop up words.
            if (m->strong) {
                // The voice detector can mistake steady hiss for speech after
                // several seconds. Track the ambient level and require speech
                // to rise above it as well as passing the detector.
                if (speech < 0.5f || m->level_smooth < m->noise_floor * 2.0f)
                    m->noise_floor += 0.01f * (m->level_smooth - m->noise_floor);
                if (speech >= 0.75f && m->level_smooth > m->noise_floor * 2.2f && m->level_smooth > 30.0f) {
                    m->speech_hold = 25;
                }
                else if (m->speech_hold) m->speech_hold--;
                float target = m->speech_hold ? 1.0f : 0.0f;
                m->gate += (target > m->gate ? 0.75f : 0.12f) * (target - m->gate);
                if (m->gate < 0.005f) m->gate = 0.0f;
            } else { m->gate = 1.0f; m->speech_hold = 0; }
            for (unsigned c = 0; c < m->channels; c++)
                for (unsigned i = 0; i < NOISE_FRAME; i++) m->output[c][i] *= m->gate;
            m->position = 0; m->ready = true;
        }
    }
    return true;
}
