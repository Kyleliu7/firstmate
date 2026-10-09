import os, pathlib, subprocess, json, shutil, time, hashlib, pty, fcntl, termios, struct, select, signal
ROOT = pathlib.Path.cwd()
EVID = pathlib.Path('/home/dapang/.no-mistakes/evidence/01M4F2GTEY0RAXNV119TBKP5JY')
LAB = ROOT / '.test-windows-trust/live'
LAB.mkdir()
log = []
results = []
def run(args, env=None, cwd=None, expected=0):
    p = subprocess.run([str(a) for a in args], env=env, cwd=cwd or ROOT, capture_output=True, timeout=20)
    encoding = 'utf-16le' if '/u' in args else 'utf-8'
    text = p.stdout.decode(encoding, 'replace') + p.stderr.decode('utf-8', 'replace')
    log.append('$ ' + ' '.join(str(a) for a in args) + '\n' + text + f'\nexit={p.returncode}\n')
    if expected is not None: assert p.returncode == expected, text
    return p, text

def git(*args): return run(['git', *args], env=git_env)
def winpath(path): return subprocess.check_output(['wslpath','-w',str(path)]).decode().strip()
def store(home): return home / '.gemini/antigravity-cli/settings.json'
def seed(home, obj):
    s=store(home); s.parent.mkdir(parents=True,exist_ok=True); s.write_text(json.dumps(obj)); return s
base_env=os.environ.copy()
for k in list(base_env):
    if k.startswith('GIT_') or k.endswith(('_API_KEY','_TOKEN')) or k in ['GEMINI_API_KEY','GOOGLE_API_KEY']: base_env.pop(k,None)
base_env['TMPDIR']=str(LAB/'temp'); pathlib.Path(base_env['TMPDIR']).mkdir()
git_env=base_env | {'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','GIT_AUTHOR_NAME':'Live Test','GIT_AUTHOR_EMAIL':'live@example.invalid','GIT_COMMITTER_NAME':'Live Test','GIT_COMMITTER_EMAIL':'live@example.invalid'}
project=LAB/'project'; wt=LAB/'wt'; link=LAB/'wt-link'; home=LAB/'linux-home'
home.mkdir(); git('init',str(project)); git('-C',str(project),'commit','--allow-empty','-m','disposable fixture'); git('-C',str(project),'worktree','add','-b','scratch',str(wt)); link.symlink_to(wt, target_is_directory=True)
other=LAB/'other'; foreign=LAB/'foreign'; git('init',str(other)); git('-C',str(other),'commit','--allow-empty','-m','disposable fixture'); git('-C',str(other),'worktree','add','-b','foreign',str(foreign))
agy=pathlib.Path(shutil.which('agy')).resolve(); cmd=pathlib.Path(subprocess.check_output(['wslpath','-u','C:\\Windows\\System32\\cmd.exe']).decode().strip())
assert agy.read_bytes()[:2]==b'MZ'; assert cmd.is_file()
log.append(f'Real selected executable: {agy}\nReal Windows cmd: {cmd}\n')
helper=ROOT/'bin/fm-agy-trust.sh'
keep={'model':'keep me','trustedWorkspaces':['C:\\existing-workspace'],'custom':{'boolean':True,'number':17}}
linuxkeep={'untouched':True}
def isolated(profile, onpath=False):
    profile.mkdir(exist_ok=True)
    dirs={'USERPROFILE':profile,'HOME':home,'APPDATA':profile/'AppData/Roaming','LOCALAPPDATA':profile/'AppData/Local','TEMP':profile/'Temp','TMP':profile/'Temp'}
    for d in dirs.values(): d.mkdir(parents=True,exist_ok=True)
    env=base_env.copy()
    env.update({k:str(v) for k,v in dirs.items()})
    env['WSLENV']=':'.join(k+'/p' for k in dirs)
    if onpath: env['PATH']=str(cmd.parent)+':'+env['PATH']
    return env

def scenario(name, fn):
    try:
        reason=fn() or ''
        results.append({'name':name,'result':'pass','live':True,'reason':reason,'evidence':'live-trust.log'})
    except Exception as e:
        results.append({'name':name,'result':'fail','live':True,'reason':repr(e),'evidence':'live-trust.log'})
        log.append('FAIL: '+repr(e))

profile=LAB/'Windows profile'; env=isolated(profile)
win_store=seed(profile,keep); linux_store=seed(home,linuxkeep)
# Real wslpath canonicalizes this symlink, so translated logical and real
# paths coincide. The persisted array contract requires one copy of each.
want=list(dict.fromkeys([winpath(link),winpath(wt)]))
log.append('Real wslpath logical/resolved translations: '+repr(want)+'\n')

def windows():
    # The default PATH has no cmd.exe: the product must use its real System32 fallback.
    assert shutil.which('cmd.exe',path=env['PATH']) is None
    run([helper,link,project,shutil.which('agy')],env)
    got=json.loads(win_store.read_text())
    assert got==keep | {'trustedWorkspaces':keep['trustedWorkspaces']+want}, got
    assert json.loads(linux_store.read_text())==linuxkeep
    before=win_store.read_bytes(); run([helper,link,project,agy],env); assert win_store.read_bytes()==before
    log.append('Persisted Windows public settings contract:\n'+win_store.read_text()+'\nLinux store stayed unchanged; repeat registration is byte-identical.\n')
scenario('Register a symlinked Linux worktree for Windows agy using the System32 fallback, preserving settings and avoiding the Linux store',windows)

def unicode():
    for name in ['René','Probe & Name','René & Name']:
        profile2=LAB/name; s=seed(profile2,keep)
        for onpath in [False,True]:
            env2=isolated(profile2,onpath)
            p,_=run([cmd,'/d','/u','/c','set USERPROFILE'],env2)
            actual=p.stdout.decode('utf-16le').strip(); assert actual=='USERPROFILE='+winpath(profile2),repr(actual)
            seed(profile2,keep); run([helper,link,project,agy],env2)
            got=json.loads(s.read_text()); assert got==keep | {'trustedWorkspaces':keep['trustedWorkspaces']+want},got
            assert json.loads(linux_store.read_text())==linuxkeep
            log.append(f'UTF-16 Windows environment listing (decoded): {actual}\nPersisted settings: {s.read_text()}\n')
scenario('Register accented and ampersand-containing Windows profiles through real cmd.exe without corrupting the profile path',unicode)

def native():
    for executable in [[],['/bin/bash']]:
        seed(home,keep); before=win_store.read_bytes()
        run([helper,link,project,*executable],env)
        assert json.loads(linux_store.read_text())==keep | {'trustedWorkspaces':keep['trustedWorkspaces']+[str(link),str(wt)]}
        assert win_store.read_bytes()==before
        log.append('Native Linux persisted settings:\n'+linux_store.read_text()+'\n')
    seed(home,linuxkeep)
scenario('Omit the executable or select a native executable and keep registration in the Linux profile',native)

def guards():
    sub=wt/'subdirectory'; sub.mkdir(); plain=LAB/'plain'; plain.mkdir()
    for path in [project,home,plain,sub,foreign]:
        before=(win_store.read_bytes(),linux_store.read_bytes())
        p,_=run([helper,path,project,agy],env,expected=None)
        assert p.returncode!=0; assert before==(win_store.read_bytes(),linux_store.read_bytes())
    log.append('All scope refusals left both profiles byte-identical.\n')
scenario('Attempt to trust a primary checkout, home, plain folder, subfolder, and unrelated worktree and observe refusal without profile writes',guards)

def invalid():
    for raw in ['{not json','{"trustedWorkspaces":false,"other":17}']:
        win_store.write_text(raw); before=linux_store.read_bytes()
        p,_=run([helper,wt,project,agy],env,expected=None); assert p.returncode!=0
        assert win_store.read_text()==raw; assert linux_store.read_bytes()==before
    seed(profile,keep)
    bad=env.copy(); bad['USERPROFILE']='%USERPROFILE%'; bad['WSLENV']='USERPROFILE:'+':'.join(k+'/p' for k in ['HOME','APPDATA','LOCALAPPDATA','TEMP','TMP'])
    before=(win_store.read_bytes(),linux_store.read_bytes())
    p,_=run([helper,wt,project,agy],bad,expected=None); assert p.returncode!=0; assert before==(win_store.read_bytes(),linux_store.read_bytes())
    log.append('Malformed settings and nonabsolute Windows USERPROFILE were refused; both profiles preserved.\n')
scenario('Supply malformed Windows settings or an unproven Windows home and observe refusal rather than Linux fallback',invalid)

# Regression oracle: Windows agy consumes Windows/UNC trust, never the Linux store.
seed(home,linuxkeep); seed(profile,keep)
p,_=run([ROOT/'.test-windows-trust/baseline-trust.sh',link,project],env)
assert json.loads(win_store.read_text())==keep
assert str(wt) in json.loads(linux_store.read_text())['trustedWorkspaces']
log.append('Before-fix helper reproduced the reported wrong-profile behavior: Windows settings unchanged, Linux trust written.\n')
seed(home,linuxkeep); seed(profile,keep); run([helper,wt,project,agy],env)

# Real interactive product with a correctly sized, drained pseudo-terminal.
master,slave=pty.openpty(); fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,120,0,0))
def setup():
    os.setsid(); fcntl.ioctl(0,termios.TIOCSCTTY,0)
p=subprocess.Popen([str(agy)],cwd=wt,env=env,stdin=slave,stdout=slave,stderr=slave,preexec_fn=setup)
os.close(slave); chunks=[]; start=time.monotonic()
try:
    while time.monotonic()-start<45 and p.poll() is None:
        ready,_,_=select.select([master],[],[],0.2)
        if ready:
            try: data=os.read(master,65536)
            except OSError: break
            chunks.append(data)
            if b'\x1b[6n' in data: os.write(master,b'\x1b[1;1R')
    (EVID/'agy-interactive.ansi').write_bytes(b''.join(chunks))
    log.append(f'Interactive launch: {agy}, cwd={wt}, disposable USERPROFILE={profile}, pty=120x40, elapsed={time.monotonic()-start:.1f}s. No trust answer or login was sent.\n')
finally:
    if p.poll() is None:
        os.write(master,b'\x03'); time.sleep(1)
        if p.poll() is None: os.killpg(p.pid,signal.SIGTERM)
        try: p.wait(timeout=3)
        except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
    os.close(master)

import pyte
screen=pyte.Screen(120,40); stream=pyte.Stream(screen); stream.feed(b''.join(chunks).decode('utf8','replace'))
visible='\n'.join(screen.display); (EVID/'agy-screen.txt').write_text(visible)
from PIL import Image, ImageDraw, ImageFont
fontpath=subprocess.check_output(['fc-match','-f','%{file}','monospace']).decode()
font=ImageFont.truetype(fontpath,15); image=Image.new('RGB',(120*9+24,40*20+24),'#111111'); draw=ImageDraw.Draw(image)
colors={'default':'#eeeeee','black':'#000000','red':'#cc4444','green':'#66cc66','brown':'#dddd66','blue':'#6666dd','magenta':'#cc66cc','cyan':'#66cccc','white':'#eeeeee'}
for row in range(40):
    for col in range(120):
        cell=screen.buffer[row][col]; color=colors.get(cell.fg,'#'+cell.fg if len(cell.fg)==6 else '#eeeeee')
        draw.text((12+col*9,12+row*20),cell.data,font=font,fill=color)
image.save(EVID/'agy-interactive.png')
log.append('Final real terminal grid:\n'+visible+'\n')
# Never turn authentication-blocked absence into a proven suppression pass.
results.append({'name':'Launch Windows agy in a freshly registered Linux worktree without its folder-trust dialog','result':'untested','live':True,'evidence':'agy-interactive.png; agy-interactive.ansi','reason':'Registered a fresh scratch git worktree using the resolved Windows agy executable and real cmd.exe/wslpath, then ran the real TUI for 45 seconds with a 120x40 drained pty and disposable Windows USERPROFILE, APPDATA, LOCALAPPDATA, HOME, and temp directories. The screen said "You are currently not signed in" and offered Google OAuth or a Google Cloud project; it never reached workspace trust. No dialog appeared, but authentication-blocked absence is not proof of suppression. An authorized preauthenticated disposable profile inside the worktree is needed; signing in or copying production credentials is outside this phase authority. Removed only the scratch trust entry, verified other keys preserved, and deleted the scratch repo/profile.'})
# Remove only the scratch entry, preserving every other key/entry, before deleting the lab.
got=json.loads(win_store.read_text()); got['trustedWorkspaces']=[x for x in got['trustedWorkspaces'] if x!=winpath(wt)]; win_store.write_text(json.dumps(got)); assert got==keep
log.append('Removed the scratch trust entry; every other settings key and existing trust entry preserved. Disposable repos and profiles deleted.\n')
(EVID/'live-trust.log').write_text('\n'.join(log)); (EVID/'live-scenarios.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
shutil.rmtree(LAB)
print(json.dumps(results,ensure_ascii=False,indent=2))
