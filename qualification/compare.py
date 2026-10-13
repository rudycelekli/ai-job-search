import argparse,datetime,hashlib,json,pathlib,re
P=pathlib.Path;H=P(__file__).resolve().parent;M=json.loads((H/'manifest.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
NEW={'tests.test_rank_state.Apply.'+n for n in M['new_methods']}
def load(p):return json.loads(p.read_text())
def labels(lane,phase):
    if lane.startswith('python-'):return ['runtime','dependencies','original','baseline-regressions'] if phase=='baseline' else ['runtime','dependencies','fixed']
    if lane=='guards':return ['runtime','dependencies','bind-base','lint_skills','check_framework_version','security_guards','placeholders']
    if lane=='bun':
        out=['runtime','bun-runtime']
        for i,x in enumerate(M['bun_clis']):
            out+=['bun-install-'+str(i),'bun-typecheck-'+str(i)]
            if x['tests']:out+=['bun-test-'+str(i)]
        return out
    assert lane in {'latex-latest','latex-bookworm'}
    return ['runtime']+(['apt-update','apt-install'] if lane=='latex-bookworm' else ['pdf-tools'])+['lualatex-version','xelatex-version','pdfinfo-version','pdftotext-version','compile-main_example','extract-main_example','compile-cover_example','extract-cover_example','cv-stock','cover-stock']

def command(lane,label,root,exe,harness=None,proof=None,parent_netns=None):
    cwd=root
    if label=='runtime':return ([exe,'--version'],cwd)
    if label=='dependencies':return ([exe,'-m','pip','install','openpyxl==3.1.5' if lane.startswith('python-') else 'pyyaml'],cwd)
    if label in {'original','fixed'}:return ([exe,'-m','unittest','discover','-s','tests','-t','.','-v'],cwd)
    if label=='baseline-regressions':return ([exe,'-m','unittest','tests.test_rank_state','-v'],cwd)
    if label=='bind-base':return (['git','update-ref','refs/remotes/origin/qualification-immutable-base',M['base']],cwd)
    if label in {'lint_skills','check_framework_version','security_guards'}:return ([exe,'tools/'+label+'.py'],cwd)
    if label=='placeholders':return (['bash','-eu','-c',M['placeholder_script']],cwd)
    if label=='bun-runtime':return (['bun','--version'],cwd)
    if label.startswith('bun-'):
        i=int(label.rsplit('-',1)[1]);cwd=str(P(root)/M['bun_clis'][i]['directory'])
        if label.startswith('bun-test-'):
            assert harness and proof
            return (['sudo','-n','--preserve-env=PATH','unshare','--net',exe,str(P(harness)/'network_namespace.py'),'--proof',str(P(proof)/(label+'-network.json')),'--cwd',cwd,'--parent-netns',parent_netns,'--','bun','test'],cwd)
        return ({'bun-install':['bun','install'],'bun-typecheck':['bun','run','typecheck']}[label.rsplit('-',1)[0]],cwd)
    if label=='apt-update':return (['apt-get','update'],cwd)
    if label=='apt-install':return (['apt-get','install','-y','--no-install-recommends','texlive-luatex','texlive-latex-extra','texlive-xetex','texlive-fonts-extra','texlive-fonts-recommended','poppler-utils','python3'],cwd)
    if label=='pdf-tools':return (['bash','-eu','-c','if ! command -v pdfinfo >/dev/null || ! command -v pdftotext >/dev/null; then apt-get update; apt-get install -y --no-install-recommends poppler-utils; fi'],cwd)
    if label in {'lualatex-version','xelatex-version','pdfinfo-version','pdftotext-version'}:
        tool=label.removesuffix('-version');return ([tool,'--version' if tool in {'lualatex','xelatex'} else '-v'],cwd)
    if label.startswith('compile-'):
        cv=label=='compile-main_example';return (['lualatex' if cv else 'xelatex','-interaction=nonstopmode','-halt-on-error','main_example.tex' if cv else 'cover_example.tex'],str(P(root)/('cv' if cv else 'cover_letters')))
    if label.startswith('extract-'):return ([exe,'tools/verify_pdf.py','cv/main_example.pdf' if label=='extract-main_example' else 'cover_letters/cover_example.pdf','--min-chars','100'],cwd)
    if label=='cv-stock':return ([exe,'tools/verify_pdf.py','cv/main_example.pdf','--pages','2','--ascii-dates','--contains','[your.email@example.com]','--contains','Professional Experience','--contains','Achievement'],cwd)
    if label=='cover-stock':return ([exe,'tools/verify_pdf.py','cover_letters/cover_example.pdf','--pages','1','--contains','your.email@example.com','--contains','Dear [Hiring Manager / Team]'],cwd)
    raise AssertionError('unknown canonical command')

def inspect(path,phase,lane):
    x=load(path/'native.json');assert x['result']=='PASS';assert x['phase']==phase and x['lane']==lane;assert x['head']==M['base' if phase=='baseline' else 'head']
    assert x['helpers']=={name:sha((H/name).read_bytes()) for name in M['helpers']}
    assert x['harness_before']==x['harness_after']
    source=P(x['source_root']);helper=P(x['helper_root']);harness=P(x['harness_root']);origin=P(x['proof_root'])
    assert all(p.is_absolute() and '..' not in p.parts for p in [source,helper,harness,origin])
    assert source.name=='source' and harness.name=='harness' and helper.name=='qualification'
    assert helper.parent==harness and source.parent==harness.parent
    assert origin.name==lane+'-'+phase and origin.parent.name=='proof' and origin.parent.parent==source.parent
    assert x['container']==M['containers'].get(lane,'')
    if x['container']:
        bootstrap=(path/x['bootstrap']['log']).read_bytes();assert sha(bootstrap)==x['bootstrap']['sha256'];assert bootstrap.rstrip().endswith(b'CONTAINER_BOOTSTRAP_PASS')
    else:assert x['bootstrap'] is None
    assert x['platform']['system']=='Linux'
    assert x['reports']=={p.name:sha(p.read_bytes()) for p in path.glob('*.json') if p.name!='native.json'}
    assert labels(lane,phase)==M['command_labels'][lane][phase]
    assert [c['label'] for c in x['commands']]==M['command_labels'][lane][phase]
    assert x['commands']
    for c in x['commands']:
        start=datetime.datetime.fromisoformat(c['start']);end=datetime.datetime.fromisoformat(c['end'])
        assert start.utcoffset()==end.utcoffset()==datetime.timedelta(0) and start<=end
        assert (c['argv'],c['cwd'])==command(lane,c['label'],x['source_root'],x['python_executable'],x['helper_root'],x['proof_root'],x['parent_net_namespace'])
        
        if c['label'] in {'original','fixed'}:assert c['argv'][1:]==['-m','unittest','discover','-s','tests','-t','.','-v']
        if c['label']=='baseline-regressions':assert c['argv'][1:]==['-m','unittest','tests.test_rank_state','-v']
        assert c['log']==c['label']+'.log'
        assert sha((path/c['log']).read_bytes())==c['sha256']
        assert c['exit']==(1 if c['label']=='baseline-regressions' else 0)
    return x

def cases(path,label):
    rows=load(path/(label+'.json'))['rows'];starts=[r['id'] for r in rows if r['event']=='start'];assert starts and len(starts)==len(set(starts))
    outcomes={};subs={}
    for r in rows:
        if r['event']=='outcome':assert r['id'] not in outcomes;outcomes[r['id']]=(r['outcome'],r['detail'])
        elif r['event']=='subtest':assert r['id'] not in subs;subs[r['id']]=(r['parent'],r['outcome'])
        else:assert r['event']=='start'
    # Failing subtests make the parent fail without a separate addFailure callback.
    for ident in starts:
        if ident not in outcomes:
            failures=[v[1] for v in subs.values() if v[0]==ident and v[1]!='pass'];assert failures;outcomes[ident]=('subtest_failure',None)
    assert set(starts)==set(outcomes)
    assert all(parent in outcomes and ident.startswith(parent+' (') for ident,(parent,outcome) in subs.items())
    for parent in starts:
        if outcomes[parent][0]=='pass':assert all(v[1]=='pass' for v in subs.values() if v[0]==parent)
    return outcomes,subs

def bun_cases(path,label):
    text=(path/(label+'.log')).read_text();rows=[];file=None
    for line in text.splitlines():
        if re.fullmatch(r'[^\s].*\.(?:test|spec)\.[tj]sx?:',line):file=line[:-1]
        match=re.fullmatch(r'\((pass|fail|skip|todo)\) (.*?)(?: \[\d+(?:\.\d+)?(?:ms|s)\])?',line)
        if match:
            assert file is not None;rows.append((file,match.group(2),match.group(1)))
    assert rows and len(rows)==len(set(rows));assert all(r[2] in {'pass','skip','todo'} for r in rows)
    counts={}
    for line in text.splitlines():
        match=re.fullmatch(r'\s*(\d+) (pass|fail|skip|todo)\s*',line)
        if match:assert match[2] not in counts;counts[match[2]]=int(match[1])
    assert 'pass' in counts and 'fail' in counts
    assert counts['fail']==0
    assert all(sum(row[2]==outcome for row in rows)==counts.get(outcome,0) for outcome in ['pass','fail','skip','todo'])
    summary=re.findall(r'Ran (\d+) tests? across (\d+) files?',text);assert len(summary)==1
    assert int(summary[0][0])==len(rows) and int(summary[0][1])==len({r[0] for r in rows})
    return rows

def inspect_network(x,cwd,parent_netns):
    assert x['status']=='PASS' and x['command']==['bun','test'] and x['cwd']==cwd
    assert {r['ifname'] for r in x['links']}=={'lo'}
    assert all(r.get('dev')=='lo' and r.get('type') in {'local','broadcast'} for r in x['routes'])
    assert all(r.get('dev')=='lo' and r.get('type') in {'local','multicast','unicast'} and r.get('dst') in {'::1','ff00::/8'} for r in x['ipv6_routes'])
    assert x['loopback']=='PASS' and x['external_documentation_address']=='203.0.113.1'
    assert x['external_errno']==101 and x['external_result']=='ENETUNREACH'
    assert x['external_ipv6_documentation_address']=='2001:db8::1' and x['external_ipv6_errno']==101 and x['external_ipv6_result']=='ENETUNREACH'
    assert x['parent_net_namespace']==parent_netns and x['net_namespace']!=parent_netns
    assert re.fullmatch(r'net:\[\d+\]',x['net_namespace']) and x['pid']>0
    assert set(x['environment'])=={'PATH'} and x['environment']['PATH']
    assert set(x['executables'])=={'bun','ip','unshare','sudo'} and all(P(value).is_absolute() for value in x['executables'].values())
    assert set(x['versions'])=={'unshare','ip','sudo'} and all(x['versions'].values())

def pair(base,fixed,lane):
    b=inspect(base,'baseline',lane);f=inspect(fixed,'fixed',lane)
    assert b['python']==f['python']
    assert (base/'runtime.log').read_bytes()==(fixed/'runtime.log').read_bytes()
    assert all(b['platform'][key]==f['platform'][key] for key in ['system','machine'])
    if lane.startswith('latex-'):
        for tool in ['lualatex','xelatex','pdfinfo','pdftotext']:assert (base/(tool+'-version.log')).read_bytes()==(fixed/(tool+'-version.log')).read_bytes()
    assert set(b['before'])==set(f['before'])
    changed={p for p in b['before'] if b['before'][p]!=f['before'][p]};assert changed==set(M['files'])
    for p,digest in M['files'].items():
        assert f['before'][p]['sha256']==digest
        assert b['before'][p]['sha256']==M['baseline_files'][p]
    if lane.startswith('python-'):
        bo,bs=cases(base,'original');fo,fs=cases(fixed,'fixed')
        assert all(v[0] in {'pass','skip','expected_failure'} for v in bo.values());assert all(v[0] in {'pass','skip','expected_failure'} for v in fo.values())
        new=set(fo)-set(bo);assert new==NEW,(new,NEW)
        assert all(fo[n]==('pass',None) for n in NEW)
        assert {k:v for k,v in fo.items() if k not in NEW}==bo
        assert {k:v for k,v in fs.items() if v[0] not in NEW}==bs
        co,cs=cases(base,'baseline-regressions');assert set(NEW)<=set(co)
        fails={k for k,v in cs.items() if v[1]=='fail'};assert fails==set(M['expected_baseline_failure_subtests'])
        assert {k:v[0] for k,v in fs.items() if v[0] in NEW}=={k:v[0] for k,v in cs.items() if v[0] in NEW}
        assert all(v[1]=='pass' for v in fs.values() if v[0] in NEW)
        assert {k:v for k,v in cs.items() if v[0] not in NEW}=={k:v for k,v in bs.items() if k in cs}
        assert not any(v[1]=='error' for v in cs.values());assert {v[0] for v in cs.values() if v[1]=='fail'}==NEW-{'tests.test_rank_state.Apply.test_past_deadline_does_not_bypass_scoring_errors'}
        assert all(v[0]=='pass' for k,v in co.items() if k not in NEW);assert co['tests.test_rank_state.Apply.test_past_deadline_does_not_bypass_scoring_errors']==('pass',None)
        return {'original':len(bo),'fixed':len(fo),'new':len(NEW),'original_skips':sum(v[0]=='skip' for v in bo.values()),'baseline_regression_failures':len(fails)}
    if lane=='bun':
        assert (base/'bun-runtime.log').read_bytes()==(fixed/'bun-runtime.log').read_bytes()
        for i,cli in enumerate(M['bun_clis']):
            if cli['tests']:
                label='bun-test-'+str(i)
                assert bun_cases(base,label)==bun_cases(fixed,label)
                for path,native in [(base,b),(fixed,f)]:
                    network=load(path/(label+'-network.json'));inspect_network(network,str(P(native['source_root'])/cli['directory']),native['parent_net_namespace'])
    return {'canonical_commands_baseline':len(b['commands']),'canonical_commands_fixed':len(f['commands'])}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifacts');p.add_argument('--output',required=True);a=p.parse_args();root=P(a.artifacts);result={}
    for lane in ['python-'+v for v in ['3.10','3.11','3.12','3.13','3.14']]+['guards','bun','latex-latest','latex-bookworm']:
        result[lane]=pair(root/(lane+'-baseline'),root/(lane+'-fixed'),lane)
    P(a.output).write_text(json.dumps({'status':'PASS','pairs':result},indent=2)+'\n')
