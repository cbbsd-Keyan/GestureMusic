"""Play an exported comparison with the project's original MIDI instrument settings."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/music'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('piece',choices=['old_C','old_Am','new_1524','new_1528'])
    parser.add_argument('variant',choices=['A_solo','B_simple','C_frozen','D_pre_dynamic','E_current_static','F_dynamic'])
    parser.add_argument('--device',type=int,required=True)
    parser.add_argument('--same-tempo',action='store_true')
    args=parser.parse_args()
    from midi_engine import MidiEngine
    data=json.loads((Path(__file__).parent/args.piece/(args.variant+'.json')).read_text(encoding='utf-8'))
    factor=data['bpm']/data['score_bpm'] if args.same_tempo else 1.
    engine=MidiEngine(args.device)
    try:
        start=time.perf_counter()
        for t,kind,note,velocity in data['events']:
            while (remaining:=t*factor-(time.perf_counter()-start))>0:
                time.sleep(min(.01,remaining))
            if kind=='drum':engine.play_drum(note,velocity)
            else:
                part,action=kind.split('_')
                fn=getattr(engine,('play_' if action=='on' else 'stop_')+part)
                fn(note,velocity) if action=='on' else fn(note)
    except KeyboardInterrupt:
        pass
    finally:
        for channel in (0,1,2,9):
            for note in range(128):engine.note_off(note,0,channel)
        engine.close()

if __name__=='__main__':main()
