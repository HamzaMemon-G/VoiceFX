#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>
constexpr int SR=48000;
constexpr double PI=3.14159265358979323846;
enum Preset { Pass, Deep, Radio, Robot };
const char* names[]={"passthrough","deep","radio","robot"};
Preset preset(const std::string& s) { for(int i=0;i<4;++i) if(s==names[i]) return Preset(i); throw std::runtime_error("Unknown preset: "+s); }
float bound(float x) { return std::max(-1.0f,std::min(1.0f,x)); }

struct EffectSettings {
    int pitch=9,style=0,drive=70,noise=0,squelch=-65,clarity=35;
};
// Direct-form II biquads give the radio steep band edges and the resonant
// midrange of a small communication speaker. Coefficients are updated only
// when controls change; filter history stays continuous while adjusting.
struct Biquad {
    double b0=1,b1=0,b2=0,a1=0,a2=0,z1=0,z2=0;
    void set(int type,double frequency,double q,double gainDb=0) {
        double w=2*PI*frequency/SR,c=std::cos(w),alpha=std::sin(w)/(2*q);
        double A=std::pow(10.0,gainDb/40),a0=1+alpha;
        if(type==0){b0=(1+c)/2;b1=-(1+c);b2=b0;a1=-2*c;a2=1-alpha;}
        else if(type==1){b0=(1-c)/2;b1=1-c;b2=b0;a1=-2*c;a2=1-alpha;}
        else {b0=1+alpha*A;b1=-2*c;b2=1-alpha*A;a0=1+alpha/A;a1=-2*c;a2=1-alpha/A;}
        b0/=a0;b1/=a0;b2/=a0;a1/=a0;a2/=a0;
    }
    float tick(float x){double y=b0*x+z1;z1=b1*x-a1*y+z2;z2=b2*x-a2*y;return float(y);}
};

// Stateful O(1) DSP per sample. Dual variable-delay heads crossfade at
// their wrap points. These are character effects, not identity conversion.
struct DSP {
    Preset mode; std::vector<float> ring; int write=0; double phase=0,osc=0;
    float hp=0,prev=0,lp=0,lp2=0,lp3=0,radioOut=0,envelope=0,gate=0;
    int hang=0,tail=0; bool gateWasOpen=false;
    uint32_t randomState=0x12345678;
    double hpA,lpA,pitchStep,threshold;EffectSettings settings;
    Biquad radioHP[2],radioLP[2],presence,cabinet,postHP,postLP[2];
    bool configured=false;
    explicit DSP(Preset p,EffectSettings s=EffectSettings()):mode(p),ring(8192,0) { configure(s); }
    void configure(EffectSettings s) {
        if(configured && s.pitch==settings.pitch && s.style==settings.style && s.drive==settings.drive && s.noise==settings.noise && s.squelch==settings.squelch && s.clarity==settings.clarity)return;
        configured=true;
        settings=s;
        // Clarity controls the communication-band width. ATC is brighter
        // and less saturated; police is punchier and has a squelch tail.
        double lo=mode==Radio?(s.style?450:650)-s.clarity*(s.style?2.0:4.0):180;
        double hi=mode==Radio?(s.style?2300:1800)+s.clarity*(s.style?13:16):mode==Deep?2600:2000+40*s.clarity;
        hpA=std::exp(-2*PI*lo/SR);lpA=1-std::exp(-2*PI*hi/SR);
        pitchStep=(1-std::pow(2.0,-s.pitch/12.0))/1440;
        threshold=std::pow(10.0,s.squelch/20.0);
        if(mode==Radio) {
            double low=s.style?600-4*s.clarity:800-4*s.clarity;
            double high=s.style?2400+13*s.clarity:1900+16*s.clarity;
            for(int i=0;i<2;++i){radioHP[i].set(0,low,0.707);radioLP[i].set(1,high,0.707);postLP[i].set(1,high,0.707);}
            postHP.set(0,low,0.707);
            presence.set(2,s.style?1850:1450,s.style?1.4:1.9,s.style?7:11);
            cabinet.set(2,s.style?1000:850,2.5,s.style?2:5);
        }
    }
    float noiseSample() {
        randomState=randomState*1664525u+1013904223u;
        return float(int32_t(randomState)/2147483648.0);
    }
    float delayed(double delay) {
        double pos=write-delay; while(pos<0) pos+=ring.size();
        int a=int(pos); float f=float(pos-a);
        return ring[a]*(1-f)+ring[(a+1)%ring.size()]*f;
    }
    float tick(float x) {
        if(mode==Pass) return x;
        if(mode==Deep) {
            ring[write]=x;
            const double span=1440; // 30 ms sweep, 5 ms minimum delay.
            double b=phase+0.5; if(b>=1) b-=1;
            float w=float(0.5-0.5*std::cos(2*PI*phase));
            float y=w*delayed(240+phase*span)+(1-w)*delayed(240+b*span);
            phase+=pitchStep; if(phase>=1) phase-=1;
            write=(write+1)%ring.size();
            // Darken the shifted voice without adding a dry, recognizable copy.
            lp+=float(lpA*(y-lp)); return float(std::tanh(1.3*lp)/1.3);
        }
        if(mode==Radio) {
            // Speech-driven squelch, bounded compression, band-limited
            // overdrive and optional low-level receiver noise. No dry mix.
            float level=std::abs(x);
            envelope+=(level>envelope?0.007f:0.0003f)*(level-envelope);
            if(envelope>threshold) hang=SR*120/1000;
            else if(hang>0) --hang;
            bool open=hang>0;
            if(gateWasOpen && !open && !settings.style) tail=SR*45/1000;
            gateWasOpen=open;
            gate+=0.003f*((open?1.0f:0.0f)-gate);
            float voice=x;
            for(int i=0;i<2;++i)voice=radioLP[i].tick(radioHP[i].tick(voice));
            voice=presence.tick(cabinet.tick(voice));
            double compression=std::max(0.35,std::min(9.0,std::sqrt(0.12/std::max(double(envelope),0.0004))));
            double drive=(settings.style?1.0:1.8)+settings.drive*(settings.style?0.025:0.055);
            // Asymmetric overload adds speaker bite. ATC stays cleaner.
            double v=voice*compression*drive;
            voice=float(std::tanh(v*(v<0 && !settings.style?1.3:1.0))*0.60);
            voice=postHP.tick(voice);
            for(int i=0;i<2;++i)voice=postLP[i].tick(voice);
            float hiss=noiseSample()*float(settings.noise/100.0)*0.018f;
            float burst=tail>0?float(tail)/(SR*45/1000):0;
            if(tail>0) --tail;
            return bound(voice*gate+hiss*(gate+burst*2));
        }
        hp=float(hpA*(hp+x-prev)); prev=x; lp+=float(lpA*(hp-lp));
        // Pure ring modulation removes the old 25% natural-voice component.
        // A harmonic carrier produces a much more obvious metallic buzz.
        double carrier=(std::sin(osc)+0.35*std::sin(3*osc))/1.35;
        float y=float(std::tanh((0.9+settings.drive*0.03)*lp)*0.8*carrier);
        osc+=2*PI*(55+settings.pitch*(40.0/9))/SR; if(osc>=2*PI) osc-=2*PI;
        return bound(float(y*(1-settings.noise/100.0)+x*(settings.noise/100.0)));
    }
    void process(const int16_t* in,int16_t* out,int frames,float gain=1) {
        for(int i=0;i<frames;++i) {
            float x=(float(in[i*2])+float(in[i*2+1]))/65536.0f;
            float y=bound(tick(x)*gain);
            int16_t v=int16_t(std::max(-32768,std::min(32767,int(std::lround(y*32768)))));
            out[i*2]=out[i*2+1]=v;
        }
    }
};

extern "C" {
__declspec(dllexport) void* fx_create(int mode) { try{return new DSP(Preset(mode));}catch(...){return nullptr;} }
__declspec(dllexport) void fx_destroy(void* p) {delete static_cast<DSP*>(p);}
__declspec(dllexport) void fx_process(void* p,const float* in,float* out,int frames,int pitch,int style,int drive,int noise,int squelch,int clarity) {
 DSP* d=static_cast<DSP*>(p);EffectSettings s;s.pitch=pitch;s.style=style;s.drive=drive;s.noise=noise;s.squelch=squelch;s.clarity=clarity;d->configure(s);
 for(int i=0;i<frames;i++)out[i]=bound(d->tick(in[i]));
}
}
