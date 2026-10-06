// The microphone never leaves this machine. VAD bounds each local Whisper request.
export class Listener {
  context!: AudioContext; stream!: MediaStream; source!: MediaStreamAudioSourceNode;
  processor!: ScriptProcessorNode; gain!: GainNode;
  chunks: Float32Array[] = []; size = 0; silence = 0; speaking = false; stopped = false; processing = false;
  preRoll: Float32Array[] = []; raf = 0; analyser!: AnalyserNode;
  constructor(public onText: (text: string) => void, public onLevel: (level: number) => void, public onError: (error: string) => void, public isBusy: () => boolean) {}
  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    this.context = new AudioContext(); await this.context.resume();
    this.source = this.context.createMediaStreamSource(this.stream);
    this.analyser = this.context.createAnalyser(); this.analyser.fftSize = 256;
    this.source.connect(this.analyser);
    this.processor = this.context.createScriptProcessor(4096,1,1);
    this.gain = this.context.createGain(); this.gain.gain.value=0;
    this.source.connect(this.processor); this.processor.connect(this.gain); this.gain.connect(this.context.destination);
    this.processor.onaudioprocess = event => {
      if (this.stopped || this.isBusy() || this.processing) {this.reset(); this.preRoll=[]; return;}
      const samples = new Float32Array(event.inputBuffer.getChannelData(0));
      const rms = Math.sqrt(samples.reduce((n,x)=>n+x*x,0)/samples.length);
      this.onLevel(Math.min(1,rms*12));
      if (!this.speaking) {this.preRoll.push(samples); if(this.preRoll.length>4)this.preRoll.shift();}
      if (rms > 0.012) {
        if(!this.speaking){ this.chunks = [...this.preRoll]; this.size=this.chunks.reduce((n,c)=>n+c.length,0); this.preRoll=[]; this.speaking=true; }
        else { this.chunks.push(samples); this.size+=samples.length; }
        this.silence = 0;
      } else if (this.speaking) {this.chunks.push(samples); this.size+=samples.length; this.silence+=samples.length/this.context.sampleRate;}
      if (this.speaking && (this.silence>0.8 || this.size/this.context.sampleRate>18)) {void this.flush();}
    };
  }
  reset(){this.chunks=[];this.size=0;this.silence=0;this.speaking=false;}
  async flush(){
    const chunks = this.chunks, size = this.size; this.reset();
    if(size/this.context.sampleRate < .4)return;
    this.processing=true;
    try {
      const samples = new Float32Array(size);let offset=0;for(const c of chunks){samples.set(c,offset);offset+=c.length;}
      const form=new FormData();form.append('audio',new Blob([encodeWav(samples,this.context.sampleRate)],{type:'audio/wav'}),'speech.wav');
      const r=await fetch('/api/transcribe',{method:'POST',headers:{'X-Jarvis-Client':'ui'},body:form});
      const data=await r.json();if(!r.ok)throw new Error(data.detail || 'Speech recognition failed.');
      if(!this.stopped && data.text)this.onText(data.text);
    } catch(e){ if(!this.stopped)this.onError((e as Error).message); }
    finally{this.processing=false;}
  }
  stop(){this.stopped=true;this.processor?.disconnect();this.source?.disconnect();this.stream?.getTracks().forEach(t=>t.stop());void this.context?.close();this.onLevel(0);}
}
function encodeWav(samples:Float32Array,rate:number){
  const buffer=new ArrayBuffer(44+samples.length*2);const view=new DataView(buffer);
  const str=(off:number,s:string)=>{for(let i=0;i<s.length;i++)view.setUint8(off+i,s.charCodeAt(i));};
  str(0,'RIFF');view.setUint32(4,36+samples.length*2,true);str(8,'WAVE');str(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);str(36,'data');view.setUint32(40,samples.length*2,true);
  samples.forEach((s,i)=>view.setInt16(44+i*2,Math.max(-1,Math.min(1,s))*32767,true));return buffer;
}
