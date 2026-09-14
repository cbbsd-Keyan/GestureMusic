"""Build a small streaming C ABI around the exact engine shipped by python-stretch 0.3.1."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'.native-build'
BUILD.mkdir(exist_ok=True)
cache=BUILD/'source-metadata.json'
if cache.exists():meta=json.loads(cache.read_text(encoding='utf-8'))
else:
    meta=json.load(urllib.request.urlopen('https://pypi.org/pypi/python-stretch/0.3.1/json'))
    cache.write_text(json.dumps(meta),encoding='utf-8')
source=next(f for f in meta['urls'] if f['packagetype']=='sdist')
archive=BUILD/'python-stretch-0.3.1.tar.gz'
if not archive.exists():
    archive.write_bytes(urllib.request.urlopen(source['url']).read())
assert hashlib.sha256(archive.read_bytes()).hexdigest()==source['digests']['sha256']
vendor=ROOT/'src/audio/native/vendor'
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        parts=Path(member.name).parts[1:]
        if not member.isfile() or '..' in parts:continue
        rel=Path(*parts)
        if rel.suffix not in ('.h','.hpp') and 'license' not in rel.name.lower():continue
        target=(vendor/rel).resolve()
        assert target.is_relative_to(vendor.resolve())
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(tar.extractfile(member).read())
headers=list(vendor.rglob('signalsmith-stretch.h'))
assert len(headers)==1,headers
vswhere=Path('C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe')
vs=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
if not vs:raise RuntimeError('MSVC x64 build tools are required')
cmd=BUILD/'build.cmd'
cmd.write_text('@echo off\ncall "'+vs+'/VC/Auxiliary/Build/vcvars64.bat"\nif errorlevel 1 exit /b 1\n'
    +'cl /nologo /O2 /EHsc /utf-8 /std:c++17 /LD /I"'+str(headers[0].parent)+'" "'+str(ROOT/'src/audio/native/stream_stretch.cpp')+'" /Fe:"'+str(ROOT/'src/audio/native/stream_stretch.dll')+'"\n',encoding='utf-8')
subprocess.run(['cmd','/c',str(cmd)],cwd=BUILD,check=True)
(vendor/'ORIGIN.json').write_text(json.dumps(dict(package='python-stretch',version='0.3.1',source_url=source['url'],sha256=source['digests']['sha256']),indent=2),encoding='utf-8')
print('BUILT',ROOT/'src/audio/native/stream_stretch.dll')
