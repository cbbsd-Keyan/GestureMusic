"""Offline checks for continuous pitch-preserving time stretch; no audio/UDP hardware."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from audio.stream_stretch import StreamStretch
from tempo_player import render, Playback


@unittest.skipUnless((ROOT/'src/audio/native/stream_stretch.dll').exists(),'Build native stream library first')
class StreamingTests(unittest.TestCase):
    def test_fixed_rates_keep_pitch_stereo_and_length(self):
        sr=44100;t=np.arange(sr*3)/sr
        x=np.stack([.2*np.sin(2*np.pi*440*t),.2*np.sin(2*np.pi*660*t)],axis=1).astype(np.float32)
        for speed in (.9,1.,1.1):
            with self.subTest(speed=speed),StreamStretch(x,sr,speed) as p:
                blocks=[]
                while (block:=p.next_block(speed)) is not None:blocks.append(block)
                y=np.concatenate(blocks)
                self.assertLessEqual(abs(len(y)-len(x)/speed),2)
                self.assertFalse(np.allclose(y[:,0],y[:,1]))
                for c,f in enumerate((440,660)):
                    z=y[sr//2:-sr//2,c];n=1<<(len(z)*8-1).bit_length()
                    peak=np.argmax(abs(np.fft.rfft(z*np.hanning(len(z)),n=n)))*sr/n
                    self.assertLess(abs(peak-f),.5)

    def test_stream_start_and_end_not_lost(self):
        sr=44100;x=np.zeros((sr*3,2),np.float32)
        x[round(.1*sr),:]=.5;x[round(2.9*sr),:]=.5
        for speed in (.9,1.1):
            with StreamStretch(x,sr,speed) as p:
                blocks=[]
                while (block:=p.next_block(speed)) is not None:blocks.append(block)
            y=np.concatenate(blocks)
            for second in (.1,2.9):
                center=round(second*sr/speed);lo=max(0,center-2205);hi=min(len(y),center+2205)
                peak=lo+np.argmax(abs(y[lo:hi,0]))
                self.assertLess(abs(peak/sr-second/speed),.025)
                self.assertGreater(np.max(abs(y[lo:hi])),.05)

    def test_dynamic_changes_preserve_continuity(self):
        sr=44100;t=np.arange(sr*8)/sr
        x=np.stack([.2*np.sin(2*np.pi*440*t),.2*np.sin(2*np.pi*660*t)],axis=1).astype(np.float32)
        y,history,_=render(x,sr,[(0,1.),(2,.9),(4,1.1),(6,1.)])
        self.assertTrue(np.isfinite(y).all())
        self.assertLess(np.max(abs(np.diff(y,axis=0))),.07)
        self.assertTrue(any(abs(v-.9)<1e-6 for _,v in history))
        self.assertTrue(any(abs(v-1.1)<1e-6 for _,v in history))
        self.assertLess(max(abs(b[1]-a[1]) for a,b in zip(history,history[1:])),.005)

    def test_tiny_silence_and_invalid_speed(self):
        for count in (1,100,4410):
            with StreamStretch(np.zeros((count,2),np.float32),44100) as p:
                blocks=[]
                while (block:=p.next_block(1.)) is not None:blocks.append(block)
                y=np.concatenate(blocks)
                self.assertEqual(len(y),count);self.assertEqual(float(np.max(abs(y))),0.)
        with self.assertRaises(ValueError):StreamStretch(np.zeros((100,2),np.float32),44100,.5)

    def test_callback_drains_partial_blocks_and_reports_shortage(self):
        class Device:
            class CallbackStop(Exception):pass
        p=Playback(np.zeros((100,2),np.float32),44100,Device)
        p.queue.put((np.full((3,2),.1,np.float32),.9))
        p.queue.put((np.full((4,2),.2,np.float32),1.1))
        out=np.empty((5,2),np.float32)
        p.callback(out,5,None,False)
        np.testing.assert_allclose(out[:,0],[.1,.1,.1,.2,.2])
        p.finished.set()
        with self.assertRaises(Device.CallbackStop):p.callback(out,5,None,False)
        np.testing.assert_allclose(out[:,0],[.2,.2,0,0,0])
        self.assertEqual(p.frames,7);self.assertEqual(p.underruns,0)
        p.finished.clear();p.callback(out,5,None,True)
        self.assertEqual(p.underruns,1);self.assertEqual(p.status_events,1)

    def test_worker_failure_unblocks_startup(self):
        from unittest.mock import patch
        p=Playback(np.zeros((100,2),np.float32),44100,None)
        with patch('tempo_player.StreamStretch',side_effect=RuntimeError('native failure')):p.worker()
        self.assertEqual(p.error,'native failure')
        self.assertTrue(p.finished.is_set());self.assertTrue(p.ready.is_set())

    def test_pause_freezes_cursor_and_resume_consumes_exact_next_samples(self):
        class Device:
            class CallbackStop(Exception):pass
        p=Playback(np.zeros((1000,2),np.float32),1000,Device)
        signal=np.repeat((np.arange(1000,dtype=np.float32)/2000)[:,None],2,axis=1)
        p.queue.put((signal[:300],1.));p.queue.put((signal[300:],1.))
        out=np.empty((100,2),np.float32)
        p.callback(out,100,None,False)
        p.paused=True
        p.callback(out,100,None,False);p.callback(out,100,None,False)
        self.assertEqual(p.frames,220)
        frozen=(p.offset,p.queue.qsize(),p.frames)
        for _ in range(10):
            p.callback(out,100,None,False)
            self.assertEqual((p.offset,p.queue.qsize(),p.frames),frozen)
            self.assertTrue(np.all(out==0))
        p.paused=False;p.callback(out,100,None,False)
        expected=signal[220:320]*np.minimum(np.arange(1,101)/120,1)[:,None]
        np.testing.assert_allclose(out,expected,atol=1e-7)
        self.assertEqual(p.frames,320);self.assertEqual(p.underruns,0)

    def test_volume_ramps_and_mute_does_not_pause(self):
        class Device:
            class CallbackStop(Exception):pass
        p=Playback(np.zeros((1000,2),np.float32),1000,Device)
        p.queue.put((np.ones((1000,2),np.float32),1.))
        p.set_volume(0.)
        out=np.empty((120,2),np.float32);p.callback(out,120,None,False)
        np.testing.assert_allclose(out[:,0],1-np.arange(1,121)/120,atol=1e-7)
        p.callback(out,120,None,False)
        self.assertTrue(np.all(out==0));self.assertEqual(p.frames,240)
        p.set_volume(.5);p.callback(out,120,None,False)
        np.testing.assert_allclose(out[:,0],np.minimum(np.arange(1,121)/120,.5),atol=1e-7)
        p.set_volume(2);self.assertEqual(p.volume,1)
        p.set_volume(-1);self.assertEqual(p.volume,0)
        with self.assertRaises(ValueError):p.set_volume(float('nan'))

    def test_reverse_pause_during_fade_and_volume_change_while_paused(self):
        class Device:
            class CallbackStop(Exception):pass
        p=Playback(np.zeros((1000,2),np.float32),1000,Device)
        p.queue.put((np.ones((1000,2),np.float32),1.))
        out=np.empty((60,2),np.float32)
        p.paused=True;p.callback(out,60,None,False)
        self.assertAlmostEqual(p.transport_gain,.5)
        p.paused=False;p.callback(out,60,None,False)
        self.assertAlmostEqual(p.transport_gain,1.)
        p.paused=True
        p.callback(out,60,None,False);p.callback(out,60,None,False)
        frozen=p.frames;p.set_volume(.2)
        p.callback(out,60,None,False);self.assertEqual(p.frames,frozen)
        p.paused=False
        p.callback(out,60,None,False);p.callback(out,60,None,False)
        self.assertAlmostEqual(out[-1,0],.2,places=6)


if __name__=='__main__':unittest.main()
