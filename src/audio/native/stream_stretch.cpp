#include "signalsmith-stretch.h"
#include <cmath>

#define API extern "C" __declspec(dllexport)
using Engine=signalsmith::stretch::SignalsmithStretch<float>;
struct State { Engine engine{42}; int channels; };
struct Input {
    const float *data; int channels;
    struct Channel { const float *data; int stride; float operator[](int i) const {return data[i*stride];} };
    Channel operator[](int ch) const {return {data+ch,channels};}
};
struct Output {
    float *data; int channels;
    struct Channel { float *data; int stride; float &operator[](int i) const {return data[i*stride];} };
    Channel operator[](int ch) const {return {data+ch,channels};}
};
API void *ss_create(int channels, double sr) {
    if(channels<1 || channels>8 || !std::isfinite(sr) || sr<8000 || sr>192000)return nullptr;
    try {auto s=new State; s->channels=channels; s->engine.presetDefault(channels,sr); s->engine.setTransposeSemitones(0); return s;}
    catch(...){return nullptr;}
}
API void ss_destroy(void *p) {delete static_cast<State*>(p);}
API int ss_input_latency(void *p) {return static_cast<State*>(p)->engine.inputLatency();}
API int ss_output_latency(void *p) {return static_cast<State*>(p)->engine.outputLatency();}
API int ss_seek(void *p,const float *in,int count,double speed) {
    try {auto s=static_cast<State*>(p);s->engine.seek(Input{in,s->channels},count,speed);return 1;}catch(...){return 0;}
}
API int ss_process(void *p,const float *in,int count,float *out,int length) {
    try {auto s=static_cast<State*>(p);s->engine.process(Input{in,s->channels},count,Output{out,s->channels},length);return 1;}catch(...){return 0;}
}
API int ss_flush(void *p,float *out,int count) {
    try {auto s=static_cast<State*>(p);s->engine.flush(Output{out,s->channels},count);return 1;}catch(...){return 0;}
}
