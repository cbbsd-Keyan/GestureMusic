"""Offline read-only score audit and isolated MIDI comparison export. No API calls."""
import ast
import collections
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/music'), str(ROOT/'src/features')]
import arrangement
from motion_dynamics import MotionDynamics
OUT = ROOT/'reports/ai_listening_audit'
OUT.mkdir(exist_ok=True)

def historic(ref, path):
    source = subprocess.check_output(['git','show',f'{ref}:{path}'],cwd=ROOT)
    dest=OUT/'sources'/ref/Path(path).name
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(source)
    tree=ast.parse(source)
    # Only score construction is used; do not initialize MIDI hardware.
    tree.body=[n for n in tree.body if not (isinstance(n,ast.ImportFrom) and n.module=='midi_engine')]
    mod=types.ModuleType('audit_'+ref)
    exec(compile(tree,str(dest),'exec'),mod.__dict__)
    return mod

simple=historic('6f8dd73','src/music/score_player.py')
frozen=historic('6f8dd73','src/music/arrangement.py')
prior=historic('392c0a6','src/music/arrangement.py')

def inspect_score(path):
    s=json.loads(path.read_text(encoding='utf-8'))
    chords=sorted(s['chords'],key=lambda c:c['bar'])
    cases=[]
    strong_total=0
    for m in sorted(s['melody'],key=lambda m:(m['bar'],m['start'])):
        symbol=next((c['symbol'] for c in reversed(chords) if c['bar']<=m['bar']),None)
        strong_total+=m['start'] in (0,8)
        if m['note']%12 not in arrangement.TRIAD_PCS.get(symbol,()):
            cases.append(dict(bar_1based=m['bar']+1,start=m['start'],duration=m['dur'],note=m['note'],
                              chord=symbol,strong=m['start'] in (0,8),long=m['dur']>=4))
    return dict(file=str(path.relative_to(ROOT)),notes=len(s['melody']),strong_total=strong_total,
                strong_nonchord=sum(c['strong'] for c in cases),long_nonchord=sum(c['long'] for c in cases),
                nonchord=len(cases),cases=cases)

def vlq(n):
    out=[n&127]
    while n>>7:
        n>>=7
        out.insert(0,(n&127)|128)
    return bytes(out)

def midi(path,events):
    # 480 ticks/quarter and 120 BPM => 960 ticks/s; retain event seconds exactly to 1 tick.
    track=[]
    for ch,program in [(0,0),(1,32),(2,0)]:
        track.append((0,bytes([0xc0+ch,program])))
    for t,kind,data,velocity in events:
        ch={'melody':2,'chord':0,'bass':1,'drum':9}[kind.split('_')[0]]
        on=kind.endswith('_on') or kind=='drum'
        for note in data if isinstance(data,list) else [data]:
            assert 0<=note<=127 and 0<=velocity<=127 and t>=0
            track.append((round(t*960),bytes([(0x90 if on else 0x80)+ch,note,velocity if on else 0])))
            if kind=='drum':
                track.append((round(t*960),bytes([0x80+ch,note,0])))
    track.sort(key=lambda e:e[0])
    payload=b'\x00\xff\x51\x03\x07\xa1\x20'
    last=0
    for tick,msg in track:
        payload+=vlq(tick-last)+msg
        last=tick
    payload+=b'\x00\xff\x2f\x00'
    data=b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(payload))+payload
    path.write_bytes(data)
    assert path.read_bytes()[0:4]==b'MThd'

paths=list(sorted((ROOT/'reports/batch_FINAL').glob('pV3_*.json')))
paths += [ROOT/'reports/live_demo'/n/'score.json' for n in ['20260911_152424_246405','20260911_152802_669527']]
audit=[inspect_score(p) for p in paths]
(OUT/'score_checks.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')

selected=[('old_C',ROOT/'reports/batch_FINAL/pV3_p1_1.json'),
          ('old_Am',ROOT/'reports/batch_FINAL/pV3_p1_2.json'),
          ('new_1524',paths[-2]),('new_1528',paths[-1])]
shared=ROOT/'reports/live_demo/20260911_152802_669527'
timeline=json.loads((shared/'energy_timeline.json').read_text(encoding='utf-8'))
# Common gesture control isolates score and renderer; old scores have no original motion timeline.
energy=json.loads((shared/'profile.json').read_text(encoding='utf-8'))['energy']['normalized']
manifest=[]
for code,path in selected:
    s=json.loads(path.read_text(encoding='utf-8')); original=copy.deepcopy(s)
    basic=simple.build_events(s)
    variants={'A_solo':([e for e in basic if e[1].startswith('melody')],s['bpm']),
              'B_simple':(basic,s['bpm'])}
    for label,mod in [('C_frozen',frozen),('D_pre_dynamic',prior),('E_current_static',arrangement)]:
        es,_,bpm=mod.build_arranged_events(s,energy)
        variants[label]=(es,bpm)
    es,_,bpm=arrangement.build_arranged_events(s,energy,dynamics=MotionDynamics(s,timeline,'song'))
    variants['F_dynamic']=(es,bpm)
    for label,(es,bpm) in variants.items():
        dest=OUT/code
        dest.mkdir(exist_ok=True)
        obj=dict(score=str(path.relative_to(ROOT)),variant=label,bpm=bpm,score_bpm=s['bpm'],
                 shared_control=str(shared.relative_to(ROOT)),events=es)
        (dest/(label+'.json')).write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
        midi(dest/(label+'.mid'),es)
        # Fixed score tempo comparison separates tempo effects from accompaniment changes.
        midi(dest/(label+'_same_tempo.mid'),[(t*bpm/s['bpm'],k,d,v) for t,k,d,v in es])
        manifest.append(dict(code=code,variant=label,bpm=bpm,counts=dict(collections.Counter(e[1] for e in es))))
    assert s==original
    if code.startswith('new'):
        own=json.loads((path.parent/'playback.json').read_text(encoding='utf-8'))
        midi(OUT/code/'G_actual_session.mid',own['events'])
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('scores',len(audit),'comparison variants',len(manifest),'MIDI',len(list(OUT.glob('*/*.mid'))))
old=audit[:-2]
print('FINAL strong nonchord/total',sum(a['strong_nonchord'] for a in old),sum(a['strong_total'] for a in old))
for a in audit[-2:]:print(a['file'],a['strong_nonchord'],a['strong_total'],a['long_nonchord'])
