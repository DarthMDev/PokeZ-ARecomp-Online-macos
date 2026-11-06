#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct MicNoise MicNoise;
MicNoise *mic_noise_create(unsigned channels);
void mic_noise_destroy(MicNoise *filter);
void mic_noise_set_strong(MicNoise *filter, bool strong);
bool mic_noise_process(MicNoise *filter, int16_t *samples, size_t count);
