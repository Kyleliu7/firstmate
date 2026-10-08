import os, pathlib, subprocess, json, hashlib, shutil, time
root=pathlib.Path.cwd(); lab=root/'.test-temp/live-trust'; lab.mkdir()
evidence=pathlib.Path('/home/dapang/.no-mistakes/evidence/01M4D5VRXXRT657YETY0SJJ1MT')
base={**os.environ,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','TMPDIR':str(root/'.test-temp')}
for key in list(base):
    if key.startswith('GIT_') and key not in ('GIT_CONFIG_GLOBAL','GIT_CONFIG_SYSTEM'): del base[key]
base['GIT_CONFIG_NOSYSTEM']='1'
logs=[]
def run(args,env=base,check=True):
    p=subprocess.run([str(a) for a in args],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',timeout=20)
    if check and p.returncode: raise AssertionError(p.stdout)
    return p
proj=lab/'project'; wt=lab/'wt'; link=lab/'wt-link'; home=lab/'linux-home'; home.mkdir()
run(['git','init','-q',proj]); run(['git','-C',proj,'-c','user.name=Test','-c','user.email=test@local','commit','-q','--allow-empty','-m','fixture'])
run(['git','-C',proj,'worktree','add','-q','-b','test',wt]); link.symlink_to(wt)
sub=(wt/'sub');sub.mkdir()
other=lab/'unrelated';otherwt=lab/'other-wt';run(['git','init','-q',other]);run(['git','-C',other,'-c','user.name=Test','-c','user.email=test@local','commit','-q','--allow-empty','-m','fixture']);run(['git','-C',other,'worktree','add','-q','-b','other',otherwt])
linux=home/'.gemini/antigravity-cli/settings.json'; linux.parent.mkdir(parents=True); linux.write_text('{"untouched":true}\n'); linux_before=linux.read_bytes()
agy=shutil.which('agy'); cmd=run(['wslpath','-u','C:\\Windows\\System32\\cmd.exe']).stdout.strip()
assert pathlib.Path(agy).read_bytes()[:2]==b'MZ'
win=lambda p:run(['wslpath','-w',p]).stdout.strip()
helper=root/'bin/fm-agy-trust.sh'; expected=list(dict.fromkeys([win(link),win(wt)]))
old=root/'.test-temp/fm-agy-trust-before-review.sh'; old.write_text(run(['git','show','f6b98cf:bin/fm-agy-trust.sh']).stdout);old.chmod(0o755)
(root/'.test-temp/fm-timeout-lib.sh').symlink_to(root/'bin/fm-timeout-lib.sh')
for name in ['Probe Name','René','Probe & Name','René & Name']:
    profile=lab/'profiles'/name; profile.mkdir(parents=True); store=profile/'.gemini/antigravity-cli/settings.json';store.parent.mkdir(parents=True)
    initial={'model':'preserve me','custom':{'enabled':True},'trustedWorkspaces':['C:\\already-trusted']};store.write_text(json.dumps(initial)+'\n')
    env={**base,'HOME':str(home),'USERPROFILE':win(profile),'WSLENV':'USERPROFILE'}
    probe=run([cmd,'/d','/u','/c','set USERPROFILE'],env,False)
    # cmd output is UTF-16LE, so obtain the exact bytes independently.
    raw=subprocess.check_output([cmd,'/d','/u','/c','set USERPROFILE'],env=env,stderr=subprocess.DEVNULL)
    assert 'USERPROFILE='+win(profile) in raw.decode('utf-16le')
    logs.append('REAL CMD Unicode environment probe: '+raw.decode('utf-16le').strip())
    p=run([helper,link,proj,agy],env); result=json.loads(store.read_text())
    assert result=={**initial,'trustedWorkspaces':initial['trustedWorkspaces']+expected}; assert linux.read_bytes()==linux_before
    logs.extend(['WINDOWS '+name+': '+p.stdout.strip(),json.dumps(result,ensure_ascii=False,indent=2),'Linux store remained '+linux.read_text().strip()])
    before=store.read_bytes();run([helper,link,proj,agy],env);assert store.read_bytes()==before
    if '&' in name or 'é' in name:
        store.write_text(json.dumps(initial)+'\n');before=store.read_bytes();p=run([old,link,proj,agy],env,False);assert p.returncode!=0 and store.read_bytes()==before and linux.read_bytes()==linux_before
        logs.append('BEFORE REVIEW FIX '+name+': exit '+str(p.returncode)+'; '+p.stdout.strip())
        run([helper,link,proj,agy],env)
    # Public safety guard must reject these actual filesystem inputs before any write.
    before=store.read_bytes()
    for path in [proj,home,sub,otherwt]:
        p=run([helper,path,proj,agy],env,False);assert p.returncode!=0;assert store.read_bytes()==before and linux.read_bytes()==linux_before
        logs.append('REFUSED '+str(path.relative_to(root))+': '+p.stdout.strip())
    badenv={**env,'USERPROFILE':'%USERPROFILE%'};p=run([helper,wt,proj,agy],badenv,False);assert p.returncode!=0 and store.read_bytes()==before and linux.read_bytes()==linux_before;logs.append('UNPROVEN PROFILE: '+p.stdout.strip())
    badenv={**env,'USERPROFILE':win(profile/'missing')};p=run([helper,wt,proj,agy],badenv,False);assert p.returncode!=0 and store.read_bytes()==before and linux.read_bytes()==linux_before;logs.append('INACCESSIBLE PROFILE: '+p.stdout.strip())
    store.write_text('{not json\n');bad=store.read_bytes();p=run([helper,wt,proj,agy],env,False);assert p.returncode!=0 and store.read_bytes()==bad and linux.read_bytes()==linux_before;logs.append('CORRUPT STORE: '+p.stdout.strip())
    # The regular and symlinked selected PE must behave identically.
    store.unlink(); selected=lab/('agy-'+name); selected.symlink_to(pathlib.Path(agy).resolve());p=run([helper,link,proj,selected],env);assert json.loads(store.read_text())=={'trustedWorkspaces':expected};logs.append('PE WITHOUT EXE SUFFIX: '+p.stdout.strip())
# Native explicit binary named .exe must still use Linux HOME, as must two-argument legacy callers.
native=lab/'native.exe';native.symlink_to(shutil.which('node'));nativeenv={**base,'HOME':str(home)}
for args in [[helper,link,proj,native],[helper,link,proj]]:
    linux.write_text(json.dumps({'model':'native','trustedWorkspaces':['/existing']})+'\n');p=run(args,nativeenv);data=json.loads(linux.read_text());assert data=={'model':'native','trustedWorkspaces':['/existing',str(link),str(wt)]};logs.extend(['NATIVE: '+p.stdout.strip(),json.dumps(data,indent=2)])
# Missing Windows translator: use only actual dependencies, not shims.
minimal=lab/'minimal';minimal.mkdir()
for tool in ['bash','node','git','dirname']:(minimal/tool).symlink_to(shutil.which(tool))
linux_before=linux.read_bytes();p=run([helper,wt,proj,agy],{**nativeenv,'PATH':str(minimal)},False);assert p.returncode!=0 and linux.read_bytes()==linux_before;logs.append('MISSING WSLPATH: '+p.stdout.strip())
(evidence/'live-trust-transcript.txt').write_text('\n\n'.join(logs)+'\n')
print('Live helper scenarios completed with real cmd.exe /u, real wslpath, installed Windows agy PE, and disposable Git worktrees.')
