#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../runtime/services/audio_in.c"
pthread_mutex_t g_klock = PTHREAD_MUTEX_INITIALIZER;
static KEvent event;
Settings g_settings = {.mic_gain = 1.0f};
void kernel_signal(KObject *o) { o->signaled = true; }
KEvent *kernel_create_event_pair(uint32_t *w, uint32_t *r) { *w=1; *r=2; return &event; }
Service *service_new(const char *n, ServiceHandler h, void *v) { Service *s=calloc(1,sizeof *s); s->name=n; s->handler=h; s->state=v; return s; }
void ipc_return_object(IpcResp *r, Service *s) { r->objects[r->nobjects++]=s; }
int main(void) {
    SDL_AudioSpec spec={SDL_AUDIO_S16,1,48000}; AudioIn a={0}; a.state=1; a.rate=48000; a.channels=1; a.event=&event; a.gain=1.0f; a.applied_gain=-1.0f;
    pthread_mutex_init(&a.lock,NULL); a.stream=SDL_CreateAudioStream(&spec,&spec); assert(a.stream);
    assert(!pthread_create(&a.thread,NULL,input_thread,&a)); Service svc={.state=&a};
    unsigned char samples[128], output[128]={0}; for (int i=0;i<128;i++) samples[i]=(unsigned char)(i*7);
    uint64_t desc[5]={0,(uint64_t)(uintptr_t)output,128,128,0},tag=42;
    IpcReq req={.cmd=8,.data=(uint8_t *)&tag,.data_size=8,.na=1,.a={{(uint64_t)(uintptr_t)desc,sizeof desc}}};
    IpcResp resp={0}; audio_input(&svc,&req,&resp); assert(!resp.result && a.count==1);
    assert(SDL_PutAudioStreamData(a.stream,samples,128)); SDL_Delay(20); assert(!event.signaled);
    pthread_mutex_lock(&a.lock); a.state=0; pthread_mutex_unlock(&a.lock);
    for (int i=0;i<100 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && !memcmp(samples,output,128)); uint64_t released=0;
    req=(IpcReq){.cmd=9,.nb=1,.b={{(uint64_t)(uintptr_t)&released,8}}}; resp=(IpcResp){0};
    audio_input(&svc,&req,&resp); assert(*(uint32_t *)resp.data==1 && released==tag);
    // Input-level changes must affect samples delivered to the mod.
    int16_t quiet[64], louder[64];
    for (int i=0;i<64;i++) quiet[i]=1000, louder[i]=0;
    uint64_t boosted[5]={0,(uint64_t)(uintptr_t)louder,sizeof louder,sizeof louder,0};
    tag=43; event.signaled=false; audio_input_set_master_gain(2.0f);
    req=(IpcReq){.cmd=8,.data=(uint8_t *)&tag,.data_size=8,.na=1,.a={{(uint64_t)(uintptr_t)boosted,sizeof boosted}}};
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result);
    assert(SDL_PutAudioStreamData(a.stream,quiet,sizeof quiet));
    for (int i=0;i<100 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && louder[0]>=1990 && louder[0]<=2010);
    memset(louder,0,sizeof louder); tag=44; event.signaled=false; audio_input_set_master_gain(8.0f);
    req=(IpcReq){.cmd=8,.data=(uint8_t *)&tag,.data_size=8,.na=1,.a={{(uint64_t)(uintptr_t)boosted,sizeof boosted}}};
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result);
    assert(SDL_PutAudioStreamData(a.stream,quiet,sizeof quiet));
    for (int i=0;i<100 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && louder[0]>=7990 && louder[0]<=8010);
    memset(louder,0,sizeof louder); tag=45; event.signaled=false; audio_input_set_master_gain(32.0f);
    req=(IpcReq){.cmd=8,.data=(uint8_t *)&tag,.data_size=8,.na=1,.a={{(uint64_t)(uintptr_t)boosted,sizeof boosted}}};
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result);
    assert(SDL_PutAudioStreamData(a.stream,quiet,sizeof quiet));
    for (int i=0;i<100 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && louder[0]>=31990 && louder[0]<=32010);
    // Enabling the optional filter creates its state and buffers its first frame.
    a.rate=48000; a.channels=1; audio_input_set_master_gain(24.0f); audio_input_set_noise_suppression(true);
    memset(louder,0,sizeof louder); tag=46; event.signaled=false;
    req=(IpcReq){.cmd=8,.data=(uint8_t *)&tag,.data_size=8,.na=1,.a={{(uint64_t)(uintptr_t)boosted,sizeof boosted}}};
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result);
    assert(SDL_PutAudioStreamData(a.stream,quiet,sizeof quiet));
    for (int i=0;i<100 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && a.noise && louder[0]==0 && a.applied_gain==6.0f);
    // Turning it off immediately resumes unfiltered audio and discards old state.
    audio_input_set_noise_suppression(false); audio_input_set_master_gain(1.0f); memset(louder,0,sizeof louder); tag=47; event.signaled=false;
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result);
    assert(SDL_PutAudioStreamData(a.stream,quiet,sizeof quiet));
    for (int i=0;i<100 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && !a.noise && louder[0]>=990 && louder[0]<=1010);
    // Identical noise-filter input at 6x and 24x must leave the filter at
    // the same pre-gain, with the latter amplified fourfold afterward.
    enum { N = 480 * 30 };
    int16_t *in = malloc(N * 2), *first = calloc(N, 2), *second = calloc(N, 2);
    assert(in && first && second);
    for (int i=0;i<N;i++) in[i]=(int16_t)((i % 48 < 24) ? 300 : -300);
    uint64_t big[5]={0,(uint64_t)(uintptr_t)first,N*2,N*2,0};
    tag=48; event.signaled=false; audio_input_set_master_gain(6.0f); audio_input_set_noise_suppression(true);
    req=(IpcReq){.cmd=8,.data=(uint8_t *)&tag,.data_size=8,.na=1,.a={{(uint64_t)(uintptr_t)big,sizeof big}}};
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result); assert(SDL_PutAudioStreamData(a.stream,in,N*2));
    for (int i=0;i<500 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && a.applied_gain==6.0f);
    audio_input_set_noise_suppression(false);
    for (int i=0;i<200;i++) {
        pthread_mutex_lock(&a.lock); bool cleared = a.noise == NULL; pthread_mutex_unlock(&a.lock);
        if (cleared) break;
        SDL_Delay(2);
    }
    pthread_mutex_lock(&a.lock); assert(a.noise == NULL); pthread_mutex_unlock(&a.lock);
    big[1]=(uint64_t)(uintptr_t)second; tag=49; event.signaled=false;
    audio_input_set_master_gain(24.0f); audio_input_set_noise_suppression(true);
    resp=(IpcResp){0}; audio_input(&svc,&req,&resp); assert(!resp.result); assert(SDL_PutAudioStreamData(a.stream,in,N*2));
    for (int i=0;i<500 && !event.signaled;i++) SDL_Delay(2);
    assert(event.signaled && a.applied_gain==6.0f);
    int compared=0;
    for (int i=0;i<N;i++) if (first[i]>=10 && first[i]<5000) {
        int delta=second[i]-4*first[i]; assert(delta>=-4 && delta<=4); compared++;
    }
    assert(compared>10); free(in); free(first); free(second);
    atomic_store(&a.quit,true); pthread_join(a.thread,NULL); SDL_DestroyAudioStream(a.stream); pthread_mutex_destroy(&a.lock);
    SDL_SetHint(SDL_HINT_AUDIO_DRIVER, "dummy");
    // OpenAudioInProtocolSpecified: u64 protocol, then sample rate and channel configuration.
    uint32_t params[6]={1,0,48000,0x20000};
    req=(IpcReq){.cmd=5,.data=(uint8_t *)params,.data_size=sizeof params}; resp=(IpcResp){0};
    audin_u(NULL,&req,&resp); assert(!resp.result && resp.nobjects==1);
    Service *opened=resp.objects[0]; assert(*(uint32_t *)resp.data==48000 && *(uint32_t *)(resp.data+4)==2);
    assert(*(uint32_t *)(resp.data+8)==2);
    req=(IpcReq){.cmd=1}; resp=(IpcResp){0}; audio_input(opened,&req,&resp); assert(!resp.result);
    req=(IpcReq){.cmd=2}; resp=(IpcResp){0}; audio_input(opened,&req,&resp); assert(!resp.result);
    opened->on_close(opened); free(opened); SDL_QuitSubSystem(SDL_INIT_AUDIO);
    puts("audio input queue and dummy device passed"); return 0;
}
