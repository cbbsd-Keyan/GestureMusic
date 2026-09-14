"""Continuous audio player with optional UDP wand transport/volume control."""
import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import time
import wave

import numpy as np
from audio.stream_stretch import StreamStretch


def load_audio(path):
    # PCM16 WAV path also works in the bundled test runtime without soundfile.
    if path.suffix.lower()=='.wav':
        try:
            with wave.open(str(path),'rb') as f:
                if f.getsampwidth()!=2:raise ValueError('Not PCM16')
                sr=f.getframerate();channels=f.getnchannels()
                data=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,channels).astype(np.float32)/32768
                return data,sr
        except (wave.Error,ValueError):pass
    import soundfile as sf
    return sf.read(str(path),dtype='float32',always_2d=True)


def render(audio,sr,schedule):
    chunks=[];frames=0;history=[]
    with StreamStretch(audio,sr) as engine:
        while True:
            target=next(speed for t,speed in reversed(schedule) if frames/sr>=t)
            chunk=engine.next_block(target)
            if chunk is None:break
            chunks.append(chunk);frames+=len(chunk)
            history.append((frames/sr,engine.speed))
        timing=dict(input_latency=engine.input_latency,output_latency=engine.output_latency,
                    processing_p95_ms=float(np.percentile(engine.process_times,95)*1000),
                    processing_max_ms=max(engine.process_times)*1000)
    return np.concatenate(chunks),history,timing


class Playback:
    def __init__(self,audio,sr,sd):
        self.audio=audio;self.sr=sr;self.sd=sd;self.target=1.;self.actual=1.
        self.queue=queue.Queue(maxsize=4);self.stop=threading.Event();self.finished=threading.Event()
        self.ready=threading.Event();self.error=None;self.underruns=0;self.status_events=0;self.clipped=0
        self.current=None;self.offset=0;self.frames=0;self.metrics={}
        self.paused=False;self.volume=1.;self.volume_gain=1.;self.transport_gain=1.
        self.fade_frames=max(1,round(.12*sr))
        self.thread=threading.Thread(target=self.worker,daemon=True)

    def set_volume(self,value):
        if not np.isfinite(value):raise ValueError('Volume must be finite')
        self.volume=max(0.,min(1.,float(value)))

    def worker(self):
        try:
            with StreamStretch(self.audio,self.sr) as engine:
                while not self.stop.is_set():
                    chunk=engine.next_block(self.target)
                    if chunk is None:break
                    if not len(chunk):continue
                    # Volume is applied at consumption time, so queued audio responds too.
                    self.clipped+=int(np.count_nonzero(abs(chunk)>1))
                    chunk=np.clip(chunk,-1,1)
                    while not self.stop.is_set():
                        try:self.queue.put((chunk,engine.speed),timeout=.05);break
                        except queue.Full:self.ready.set()
                    if self.queue.qsize()>=3:self.ready.set()
                self.metrics=dict(processing_p95_ms=float(np.percentile(engine.process_times,95)*1000) if engine.process_times else 0,
                                  processing_max_ms=max(engine.process_times,default=0)*1000)
        except Exception as exc:self.error=str(exc)
        finally:self.finished.set();self.ready.set()

    def callback(self,out,frames,info,status):
        if status:self.status_events+=1
        out.fill(0);written=0;eof=False
        paused=self.paused
        # Consume only the short fade-out, then freeze the current block cursor and queue.
        limit=min(frames,max(0,int(np.ceil(self.transport_gain*self.fade_frames-1e-7)))) if paused else frames
        while written<limit:
            if self.current is None or self.offset==len(self.current):
                try:self.current,self.actual=self.queue.get_nowait();self.offset=0
                except queue.Empty:
                    if self.finished.is_set():
                        eof=True;break
                    self.underruns+=1;break
            count=min(limit-written,len(self.current)-self.offset)
            out[written:written+count]=self.current[self.offset:self.offset+count]
            self.offset+=count;written+=count
        self.frames+=written
        if written:
            step=np.arange(1,written+1,dtype=np.float64)/self.fade_frames
            transport=np.clip(self.transport_gain+(-step if paused else step),0.,1.)
            difference=self.volume-self.volume_gain
            volume=self.volume_gain+np.sign(difference)*np.minimum(step,abs(difference))
            out[:written]*=(transport*volume)[:,None]
            self.transport_gain=float(transport[-1]);self.volume_gain=float(volume[-1])
            if self.transport_gain<1e-10:self.transport_gain=0.
        if eof:raise self.sd.CallbackStop


class ConductorControl:
    """Apply wand state to playback and report only transport state edges."""
    def __init__(self):
        self.manual_paused=False
        self.was_playing=False

    def pause(self, playback):
        self.manual_paused=True
        self.was_playing=False
        playback.paused=True

    def resume(self):
        # Resume returns to waiting-for-motion; it does not force silent audio onward.
        self.manual_paused=False
        self.was_playing=False

    def update(self, wand, reader, playback, now):
        wand.poll(reader,now)
        if self.manual_paused:
            playback.paused=True
            return None
        wand.apply(playback)
        playing=not playback.paused
        event=('wand_started' if playing else 'wand_paused') if playing!=self.was_playing else None
        self.was_playing=playing
        return event


class ConductorSession:
    """Lifecycle wrapper used by the physical desktop menu, not the keyboard trial."""
    def __init__(self, audio_path, device=None, sd_module=None, reader_factory=None, wand_factory=None):
        self.audio_path=Path(audio_path);self.device=device
        self.sd=sd_module;self.reader_factory=reader_factory;self.wand_factory=wand_factory
        self.playback=None;self.reader=None;self.wand=None;self.control=ConductorControl();self.stream=None

    def start(self):
        if self.stream is not None:raise RuntimeError('Conductor session already started')
        if self.sd is None:
            import sounddevice
            self.sd=sounddevice
        if self.reader_factory is None:
            from input.udp_reader import UDPReader
            self.reader_factory=UDPReader
        if self.wand_factory is None:
            from audio.wand_control import WandControl
            self.wand_factory=WandControl
        audio,sr=load_audio(self.audio_path)
        self.reader=self.reader_factory();self.wand=self.wand_factory()
        self.playback=Playback(audio,sr,self.sd);self.playback.transport_gain=0.;self.playback.paused=True
        self.playback.thread.start()
        if not self.playback.ready.wait(10):
            self.close();raise RuntimeError('Audio preparation timed out')
        if self.playback.error:
            error=self.playback.error;self.close();raise RuntimeError(error)
        self.stream=self.sd.OutputStream(samplerate=sr,channels=audio.shape[1],dtype='float32',blocksize=1024,
                                         latency='high',device=self.device,callback=self.playback.callback)
        self.stream.start()

    def update(self, now=None):
        if self.stream is None:return None
        if self.playback.error:return 'conductor_error'
        event=self.control.update(self.wand,self.reader,self.playback,time.monotonic() if now is None else now)
        # The worker can finish filling its queue before playback ends; stream inactivity is EOF.
        if not self.stream.active and not self.playback.paused:return 'conductor_finished'
        return event

    def pause(self):
        self.control.pause(self.playback)

    def resume(self):
        self.control.resume()

    def snapshot(self):
        if self.playback is None:return {}
        return dict(energy=self.wand.rms,tempo=self.playback.target,volume=self.playback.volume,
                    position=self.playback.frames/self.playback.sr,wand_status=self.wand.status,
                    tempo_status=self.wand.tempo_status)

    def close(self):
        if self.stream is not None:
            try:self.stream.stop();self.stream.close()
            finally:self.stream=None
        if self.playback is not None:
            self.playback.stop.set()
            if self.playback.thread.ident is not None:self.playback.thread.join(timeout=5)
        if self.reader is not None:self.reader.close()


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser()
    parser.add_argument('audio',type=Path,nargs='?',default=Path('moonlight.wav'))
    parser.add_argument('--device',type=int,default=None,help='sounddevice output index, not MIDI device index')
    parser.add_argument('--list-devices',action='store_true')
    parser.add_argument('--render-test',type=Path,help='Offline 60-second continuous speed-change WAV, no audio device')
    parser.add_argument('--seconds',type=float,default=None,help='Limit source length for testing')
    parser.add_argument('--auto-test',action='store_true',help='Automatic switch schedule for device verification')
    parser.add_argument('--wand',action='store_true',help='UDP wand controls volume and pause/resume')
    args=parser.parse_args()
    if args.wand and (args.auto_test or args.render_test):
        parser.error('--wand cannot be combined with offline/automatic speed tests')
    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices());return
    audio,sr=load_audio(args.audio)
    if args.seconds is not None:
        if args.seconds<=0:parser.error('--seconds must be positive')
        audio=audio[:round(args.seconds*sr)]
    schedule=[(0.,1.),(10.,.9),(25.,1.1),(45.,1.)]
    if args.render_test:
        result,history,metrics=render(audio[:60*sr],sr,schedule)
        args.render_test.parent.mkdir(parents=True,exist_ok=True)
        assert np.max(abs(result))<1,'Output clips; inspect before encoding'
        with wave.open(str(args.render_test),'wb') as f:
            f.setnchannels(audio.shape[1]);f.setsampwidth(2);f.setframerate(sr)
            f.writeframes(np.round(result*32767).astype('<i2').tobytes())
        args.render_test.with_suffix('.json').write_text(json.dumps(dict(schedule=schedule,history=history,metrics=metrics),indent=2),encoding='utf-8')
        print(metrics);return
    import msvcrt
    import sounddevice as sd
    playback=Playback(audio,sr,sd);playback.transport_gain=0.
    reader=None;wand=None
    try:
        if args.wand:
            from input.udp_reader import UDPReader
            from audio.wand_control import WandControl
            reader=UDPReader();wand=WandControl();playback.paused=True
        playback.thread.start()
        if not playback.ready.wait(10):raise RuntimeError('Audio preparation timed out')
        if playback.error:raise RuntimeError(playback.error)
        print('Space/P: pause/resume | +/-: volume | Q: quit')
        print('No Enter needed. No brightness filter. Keep speaker volume comfortable.')
        if wand:
            print('WAND: waiting for UDP 4210. K or pause/volume keys: manual takeover; W: return to wand.')
            print('Wand controls volume and transport; playback speed is fixed.')
        with sd.OutputStream(samplerate=sr,channels=audio.shape[1],dtype='float32',blocksize=1024,
                             latency='high',device=args.device,callback=playback.callback) as stream:
            while stream.active:
                if wand:
                    wand.poll(reader,time.monotonic());wand.apply(playback)
                if args.auto_test:
                    playback.target=next(v for t,v in reversed(schedule) if playback.frames/sr>=t)
                if msvcrt.kbhit():
                    key=msvcrt.getwch().lower()
                    if key in ('\x00','\xe0'):
                        msvcrt.getwch();continue
                    if key=='q':break
                    if wand and key in ('k',' ','p','+','=','-','_'):
                        wand.enabled=False
                    if wand and key=='w':
                        wand.enabled=True;wand.apply(playback)
                    if key in (' ','p'):playback.paused=not playback.paused
                    if key in ('+','='):playback.set_volume(playback.volume+.1)
                    if key in ('-','_'):playback.set_volume(playback.volume-.1)
                state='PAUSING' if playback.paused and playback.transport_gain>0 else 'PAUSED' if playback.paused else 'PLAYING'
                if wand:
                    print(f'\r{"WAND" if wand.enabled else "MANUAL"} {wand.status:12} gyro {wand.rms:4.2f} peak {wand.rate:4.1f}Hz {wand.tempo_status:9} ',end='')
                print(f'{"" if wand else chr(13)}{state:7} {playback.frames/sr:6.1f}s  volume {playback.volume:4.0%}  target {playback.target:.2f}x  output {playback.actual:.2f}x  buffer misses {playback.underruns}  device status {playback.status_events}   ',end='',flush=True)
                time.sleep(.1)
    except KeyboardInterrupt:pass
    finally:
        playback.stop.set()
        if playback.thread.ident is not None:playback.thread.join(timeout=5)
        if reader is not None:reader.close()
        print('\n',playback.metrics,'clipped samples:',playback.clipped)
    if playback.error:raise RuntimeError(playback.error)


if __name__=='__main__':main()
