"""Frozen native qualification. No source/test changes except literal baseline fixture."""
import argparse, ast, datetime, platform, hashlib, json, os, pathlib, subprocess, sys
P=pathlib.Path
H=P(__file__).resolve().parent
M=json.loads((H/'manifest.json').read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def git(s,*args):return subprocess.check_output(['git','-C',str(s),*args])
def tree(s):
    out={}
    for row in git(s,'ls-tree','-r','-z','HEAD').split(b'\0'):
        if not row:continue
        meta,name=row.split(b'\t',1); mode,typ,oid=meta.decode().split();name=name.decode()
        assert typ=='blob'
        p=s/name;b=os.readlink(p).encode() if mode=='120000' else p.read_bytes()
        assert b==git(s,'cat-file','blob',oid),(name,'working bytes differ from Git')
        out[name]={'mode':mode,'blob':oid,'sha256':sha(b)}
    return out
parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--phase',choices=['baseline','fixed'],required=True);parser.add_argument('--lane',required=True);parser.add_argument('--proof',required=True);a=parser.parse_args()
s=P(a.source).resolve();out=P(a.proof).resolve();out.mkdir(parents=True,exist_ok=True)
expected=M['base' if a.phase=='baseline' else 'head'];assert git(s,'rev-parse','HEAD').decode().strip()==expected
assert not git(s,'status','--porcelain');before=tree(s)
assert sha((s/'.github/workflows/ci.yml').read_bytes())==M['workflow_sha256']
assert {p.name for p in H.iterdir() if p.is_file()}==set(M['helpers'])
assert sys.platform.startswith('linux')
helpers={name:sha((H/name).read_bytes()) for name in M['helpers']}
harness_root=H.parent
harness_head=git(harness_root,'rev-parse','HEAD').decode().strip()
assert git(harness_root,'rev-parse','HEAD^').decode().strip()==M['head']
assert set(git(harness_root,'diff','--name-only','HEAD^','HEAD').decode().splitlines())=={'qualification/'+n for n in M['helpers']}|{M['qualification_workflow']}
harness_before=tree(harness_root)
container=os.environ.get('QUALIFICATION_CONTAINER','')
assert container==M['containers'].get(a.lane,'')
bootstrap=None
if container:
    raw=(out/'container-bootstrap.log').read_bytes();assert raw.rstrip().endswith(b'CONTAINER_BOOTSTRAP_PASS')
    bootstrap={'log':'container-bootstrap.log','sha256':sha(raw)}
records=[]
def run(argv,label,cwd=s,env=None,expected_exit=0):
    start=now();p=subprocess.run(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    log=p.stdout+b'\n--- STDERR ---\n'+p.stderr;lp=out/(label+'.log');lp.write_bytes(log)
    records.append({'argv':argv,'cwd':str(cwd),'label':label,'start':start,'end':now(),'exit':p.returncode,'log':lp.name,'sha256':sha(log)})
    (out/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
    assert p.returncode==expected_exit,(label,p.returncode,expected_exit)
    return p
try:
    run([sys.executable,'--version'],'runtime')
    if a.lane.startswith('python-'):
        version=a.lane.removeprefix('python-');assert '.'.join(map(str,sys.version_info[:2]))==version
        run([sys.executable,'-m','pip','install','openpyxl==3.1.5'],'dependencies')
        def tests(label,full=True):
            env=os.environ.copy();env['PYTHONPATH']=str(H);env['QUALIFICATION_UNITTEST_RECEIPT']=str(out/(label+'.json'))
            cmd=[sys.executable,'-m','unittest','discover','-s','tests','-t','.','-v'] if full else [sys.executable,'-m','unittest','tests.test_rank_state','-v']
            run(cmd,label,env=env,expected_exit=1 if label=='baseline-regressions' else 0)
        tests('original' if a.phase=='baseline' else 'fixed')
        if a.phase=='baseline':
            f=s/'tests/test_rank_state.py';original=f.read_bytes();fixture=(H/'regression-fixture.py').read_bytes();assert sha(fixture)==M['test_fixture_sha256']
            def functions(b):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(b)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
            old_functions=functions(original);new_functions=functions(fixture)
            assert all(new_functions.get(n)==body for n,body in old_functions.items())
            assert set(new_functions)-set(old_functions)==set(M['new_methods'])
            try:f.write_bytes(fixture);tests('baseline-regressions',False)
            finally:f.write_bytes(original)
    elif a.lane=='guards':
        run([sys.executable,'-m','pip','install','pyyaml'],'dependencies')
        env=os.environ.copy();env['GITHUB_BASE_REF']='qualification-immutable-base'
        run(['git','update-ref','refs/remotes/origin/qualification-immutable-base',M['base']],'bind-base')
        for name in ['lint_skills','check_framework_version','security_guards']:run([sys.executable,'tools/'+name+'.py'],name,env=env)
        # Exact literal upstream shell checks, with upstream conditional intentionally enabled.
        text=(s/'.github/workflows/ci.yml').read_text();block=text.split('      - name: Tracked template files must keep their placeholder tokens\n',1)[1].split('        run: |\n',1)[1]
        run(['bash','-eu','-c','\n'.join(line[10:] for line in block.splitlines())],'placeholders')
    elif a.lane=='bun':
        dirs=sorted(p.parent for p in s.glob('.agents/skills/*/cli/package.json'));assert len(dirs)==6
        run(['bun','--version'],'bun-runtime')
        for i,d in enumerate(dirs):
            run(['bun','install'],'bun-install-'+str(i),d);run(['bun','run','typecheck'],'bun-typecheck-'+str(i),d)
            if list((d/'tests').rglob('*.test.ts')):
                run(['sudo','-n','--preserve-env=PATH','unshare','--net',sys.executable,str(H/'network_namespace.py'),'--proof',str(out/('bun-test-'+str(i)+'-network.json')),'--cwd',str(d),'--parent-netns',os.readlink('/proc/self/ns/net'),'--','bun','test'],'bun-test-'+str(i),d)
    elif a.lane.startswith('latex-'):
        if a.lane=='latex-bookworm':
            run(['apt-get','update'],'apt-update');run(['apt-get','install','-y','--no-install-recommends','texlive-luatex','texlive-latex-extra','texlive-xetex','texlive-fonts-extra','texlive-fonts-recommended','poppler-utils','python3'],'apt-install')
        else:
            run(['bash','-eu','-c','if ! command -v pdfinfo >/dev/null || ! command -v pdftotext >/dev/null; then apt-get update; apt-get install -y --no-install-recommends poppler-utils; fi'],'pdf-tools')
        for engine,args in [('lualatex',['--version']),('xelatex',['--version']),('pdfinfo',['-v']),('pdftotext',['-v'])]:run([engine,*args],engine+'-version')
        for directory,engine,name in [('cv','lualatex','main_example'),('cover_letters','xelatex','cover_example')]:
            run([engine,'-interaction=nonstopmode','-halt-on-error',name+'.tex'],'compile-'+name,s/directory)
            assert (s/directory/(name+'.pdf')).is_file();assert not any(x.startswith('!') for x in (s/directory/(name+'.log')).read_text(errors='replace').splitlines())
            run([sys.executable,'tools/verify_pdf.py',directory+'/'+name+'.pdf','--min-chars','100'],'extract-'+name)
        run([sys.executable,'tools/verify_pdf.py','cv/main_example.pdf','--pages','2','--ascii-dates','--contains','[your.email@example.com]','--contains','Professional Experience','--contains','Achievement'],'cv-stock')
        run([sys.executable,'tools/verify_pdf.py','cover_letters/cover_example.pdf','--pages','1','--contains','your.email@example.com','--contains','Dear [Hiring Manager / Team]'],'cover-stock')
    else:raise AssertionError('unknown lane')
    assert tree(s)==before
    assert {name:sha((H/name).read_bytes()) for name in M['helpers']}==helpers
    assert tree(harness_root)==harness_before
    result='PASS'
except BaseException:
    result='FAIL';raise
finally:
    (out/'native.json').write_text(json.dumps({'phase':a.phase,'lane':a.lane,'head':expected,'before':before,'helpers':helpers,'harness_head':harness_head,'harness_before':harness_before,'harness_after':tree(harness_root),'result':result,'commands':records,'reports':{p.name:sha(p.read_bytes()) for p in out.glob('*.json') if p.name!='native.json'},'container':container,'bootstrap':bootstrap,'source_root':str(s),'helper_root':str(H),'harness_root':str(harness_root),'proof_root':str(out),'python_executable':sys.executable,'parent_net_namespace':os.readlink('/proc/self/ns/net'),'platform':{'sys':sys.platform,'system':platform.system(),'platform':platform.platform(),'machine':platform.machine()},'python':sys.version},indent=2)+'\n')
