#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../runtime/services/audio_in.c"
pthread_mutex_t g_klock = PTHREAD_MUTEX_INITIALIZER;
static KEvent event;
void kernel_signal(KObject *o) { o->signaled = true; }
KEvent *kernel_create_event_pair(uint32_t *w, uint32_t *r) { *w=1; *r=2; return &event; }
Service *service_new(const char *n, ServiceHandler h, void *v) { Service *s=calloc(1,sizeof *s); s->name=n; s->handler=h; s->state=v; return s; }
void ipc_return_object(IpcResp *r, Service *s) { r->objects[r->nobjects++]=s; }
int main(void) {
    SDL_AudioSpec spec={SDL_AUDIO_S16,1,48000}; AudioIn a={0}; a.state=1; a.event=&event;
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
    atomic_store(&a.quit,true); pthread_join(a.thread,NULL); SDL_DestroyAudioStream(a.stream); pthread_mutex_destroy(&a.lock);
    SDL_SetHint(SDL_HINT_AUDIO_DRIVER, "dummy");
    uint32_t params[6]={48000,0x20000};
    req=(IpcReq){.cmd=5,.data=(uint8_t *)params,.data_size=sizeof params}; resp=(IpcResp){0};
    audin_u(NULL,&req,&resp); assert(!resp.result && resp.nobjects==1);
    Service *opened=resp.objects[0]; assert(*(uint32_t *)(resp.data+4)==2);
    req=(IpcReq){.cmd=1}; resp=(IpcResp){0}; audio_input(opened,&req,&resp); assert(!resp.result);
    req=(IpcReq){.cmd=2}; resp=(IpcResp){0}; audio_input(opened,&req,&resp); assert(!resp.result);
    opened->on_close(opened); free(opened); SDL_QuitSubSystem(SDL_INIT_AUDIO);
    puts("audio input queue and dummy device passed"); return 0;
}
