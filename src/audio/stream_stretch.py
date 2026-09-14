"""Stateful, interleaved float32 streaming bridge. Native calls run on a worker, never the audio callback."""
import ctypes as ct
import math
from pathlib import Path
import time

import numpy as np


class StreamStretch:
    def __init__(self, audio, sample_rate, speed=1., block=1024):
        if not .9 <= speed <= 1.1:raise ValueError('speed must be in [0.9, 1.1]')
        if audio.ndim!=2 or not len(audio) or not np.isfinite(audio).all():raise ValueError('invalid audio')
        self.audio=np.ascontiguousarray(audio,dtype=np.float32)
        self.sr=sample_rate;self.block=block;self.speed=speed
        self.channels=audio.shape[1];self.position=0;self.fraction=0.
        self.done=False;self.flushed=False;self.process_times=[]
        path=Path(__file__).parent/'native/stream_stretch.dll'
        if not path.exists():raise RuntimeError('Run tools/build_stream_stretch.py first')
        self.lib=ct.CDLL(str(path))
        fptr=ct.POINTER(ct.c_float)
        signatures={
            'ss_create':([ct.c_int,ct.c_double],ct.c_void_p),
            'ss_destroy':([ct.c_void_p],None),
            'ss_input_latency':([ct.c_void_p],ct.c_int),
            'ss_output_latency':([ct.c_void_p],ct.c_int),
            'ss_seek':([ct.c_void_p,fptr,ct.c_int,ct.c_double],ct.c_int),
            'ss_process':([ct.c_void_p,fptr,ct.c_int,fptr,ct.c_int],ct.c_int),
            'ss_flush':([ct.c_void_p,fptr,ct.c_int],ct.c_int),
        }
        for name,(args,result) in signatures.items():
            f=getattr(self.lib,name);f.argtypes=args;f.restype=result
        self.handle=self.lib.ss_create(self.channels,sample_rate)
        if not self.handle:raise RuntimeError('Could not create native stretcher')
        self.input_latency=self.lib.ss_input_latency(self.handle)
        self.output_latency=self.lib.ss_output_latency(self.handle)
        self.drop=self.output_latency
        initial=self._read(self.input_latency)
        if not self.lib.ss_seek(self.handle,self.ptr(initial),len(initial),speed):
            self.close();raise RuntimeError('Native seek failed')

    @staticmethod
    def ptr(x):return x.ctypes.data_as(ct.POINTER(ct.c_float))

    def _read(self,n):
        block=np.zeros((n,self.channels),np.float32)
        count=max(0,min(n,len(self.audio)-self.position))
        if count:block[:count]=self.audio[self.position:self.position+count]
        self.position+=n
        return block

    def next_block(self,target):
        if self.done:return None
        if not math.isfinite(target) or not .9<=target<=1.1:raise ValueError('invalid target speed')
        # At most 0.2x per second: a 1.0 -> 1.1 change takes approximately 0.5 s.
        self.speed+=max(-.2*self.block/self.sr,min(.2*self.block/self.sr,target-self.speed))
        remaining=len(self.audio)+self.input_latency-self.position
        if remaining>0:
            output_count=self.block
            desired=output_count*self.speed+self.fraction
            count=int(desired);self.fraction=desired-count
            if count>remaining:
                count=remaining;output_count=max(1,round(count/self.speed))
            x=self._read(count);y=np.empty((output_count,self.channels),np.float32)
            start=time.perf_counter()
            ok=self.lib.ss_process(self.handle,self.ptr(x),len(x),self.ptr(y),len(y))
            self.process_times.append(time.perf_counter()-start)
        elif not self.flushed:
            y=np.empty((self.output_latency,self.channels),np.float32)
            ok=self.lib.ss_flush(self.handle,self.ptr(y),len(y));self.flushed=True
        else:
            self.done=True;return None
        if not ok:raise RuntimeError('Native processing failed')
        if not np.isfinite(y).all():raise RuntimeError('Non-finite audio output')
        drop=min(self.drop,len(y));self.drop-=drop
        return y[drop:]

    def close(self):
        if getattr(self,'handle',None):self.lib.ss_destroy(self.handle);self.handle=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
