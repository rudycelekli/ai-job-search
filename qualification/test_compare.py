import copy,hashlib,json,pathlib,tempfile,unittest
import compare
P=pathlib.Path
class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);self.b=self.root/'b';self.f=self.root/'f';self.b.mkdir();self.f.mkdir()
        self.new=sorted(compare.NEW);self.old='tests.example.Case.test_original'
        self.helpers={n:compare.sha((compare.H/n).read_bytes()) for n in compare.M['helpers']}
        for path,phase in [(self.b,'baseline'),(self.f,'fixed')]:
            tree={n:{'mode':'100644','blob':phase,'sha256':d if phase=='fixed' else compare.M['baseline_files'][n]} for n,d in compare.M['files'].items()}
            tree['tests/example.py']={'mode':'100644','blob':'same','sha256':'same'}
            commands=[{'argv':['python','-m','unittest','discover','-s','tests','-t','.','-v'],'cwd':'/source','label':'original' if phase=='baseline' else 'fixed','start':'2026-10-13T00:00:00+00:00','end':'2026-10-13T00:00:01+00:00','exit':0,'log':('original' if phase=='baseline' else 'fixed')+'.log','sha256':compare.sha(b'pass')}]
            (path/'full.log').write_bytes(b'pass')
            if phase=='baseline':
                (path/'reg.log').write_bytes(b'fail');commands.append(dict(commands[0],label='baseline-regressions',exit=1,log='reg.log',sha256=compare.sha(b'fail'),argv=['python','-m','unittest','tests.test_rank_state','-v']))
            native={'result':'PASS','phase':phase,'lane':'python-3.12','head':compare.M['base' if phase=='baseline' else 'head'],'helpers':self.helpers,'before':tree,'harness_before':{'same':1},'harness_after':{'same':1},'commands':commands,'container':'','bootstrap':None,'source_root':'/source','helper_root':'/harness/qualification','harness_root':'/harness','proof_root':'/proof/python-3.12-'+phase,'python_executable':'python','platform':{'system':'Linux','machine':'x86_64'},'python':'3.12.0 fixture','parent_net_namespace':'net:[1]'}
            native['commands']=[dict(commands[0],label='runtime'),dict(commands[0],label='dependencies')]+commands
            for c in native['commands']:
                c['argv'],c['cwd']=compare.command('python-3.12',c['label'],'/source','python')
                c['log']=c['label']+'.log';(path/c['log']).write_bytes(b'fail' if c['label']=='baseline-regressions' else b'pass')
            self.write(path/'native.json',native)
        self.write(self.b/'original.json',{'rows':self.rows([self.old])})
        fixed_rows=self.rows([self.old]+self.new)
        for ident in compare.M['expected_baseline_failure_subtests']:fixed_rows.append({'event':'subtest','id':ident,'parent':ident.split(' (')[0],'outcome':'pass'})
        self.write(self.f/'fixed.json',{'rows':fixed_rows})
        rows=self.rows([self.old]+self.new)
        fail_parents=[n for n in self.new if not n.endswith('test_past_deadline_does_not_bypass_scoring_errors')]
        rows=[r for r in rows if not(r['event']=='outcome' and r['id'] in fail_parents)]
        for i in range(4):rows.append({'event':'subtest','id':compare.M['expected_baseline_failure_subtests'][i],'parent':compare.M['expected_baseline_failure_subtests'][i].split(' (')[0],'outcome':'fail'})
        self.write(self.b/'baseline-regressions.json',{'rows':rows})
    def write(self,p,x):p.write_text(json.dumps(x))
    def rows(self,ids):return [r for i in ids for r in [{'event':'start','id':i},{'event':'outcome','id':i,'outcome':'pass','detail':None}]]
    def pair(self):
        for path in [self.b,self.f]:
            x=json.loads((path/'native.json').read_text());x['reports']={p.name:compare.sha(p.read_bytes()) for p in path.glob('*.json') if p.name!='native.json'};self.write(path/'native.json',x)
        return compare.pair(self.b,self.f,'python-3.12')
    def test_positive(self):self.assertEqual(self.pair()['new'],3)
    def change(self,p,fn):x=json.loads(p.read_text());fn(x);self.write(p,x)
    def test_reject_native_corruption(self):
        original=(self.f/'native.json').read_bytes()
        mutations=[lambda x:x.update(result='FAIL'),lambda x:x.update(head='wrong'),lambda x:x.update(phase='baseline'),lambda x:x.update(lane='wrong'),lambda x:x['helpers'].update({'extra':'x'}),lambda x:x['helpers'].pop('native.py'),lambda x:x['helpers'].update({'native.py':'altered'}),lambda x:x.update(harness_after={}),lambda x:x['commands'][0].update(exit=1),lambda x:x['commands'][0].update(sha256='wrong'),lambda x:x['commands'][0].update(start='2027-01-01T00:00:00+00:00'),lambda x:x['commands'][0].update(cwd=''),lambda x:x['before'].pop('tests/example.py'),lambda x:x['before']['tests/example.py'].update(sha256='changed'),lambda x:x['before']['tools/rank_state.py'].update(sha256='wrong')]
        for index,mutation in enumerate(mutations):
            with self.subTest(index=index):
                (self.f/'native.json').write_bytes(original);self.change(self.f/'native.json',mutation)
                with self.assertRaises((AssertionError,KeyError)):self.pair()
        (self.f/'native.json').write_bytes(original)
    def test_reject_case_corruption(self):
        original=(self.f/'fixed.json').read_bytes()
        mutations=[lambda x:x['rows'].pop(),lambda x:x['rows'].extend(self.rows(['extra'])),lambda x:x['rows'][1].update(outcome='fail'),lambda x:x['rows'][1].update(outcome='error'),lambda x:x['rows'][1].update(outcome='skip',detail='new skip'),lambda x:x['rows'].append(x['rows'][1]),lambda x:x['rows'][3].update(outcome='skip',detail='new regression skip')]
        for index,mutation in enumerate(mutations):
            with self.subTest(index=index):
                (self.f/'fixed.json').write_bytes(original);self.change(self.f/'fixed.json',mutation)
                with self.assertRaises(AssertionError):self.pair()
        (self.f/'fixed.json').write_bytes(original)
    def test_reject_baseline_original_failure(self):
        self.change(self.b/'original.json',lambda x:x['rows'][1].update(outcome='fail'))
        with self.assertRaises(AssertionError):self.pair()
    def test_reject_changed_original_skip_reason(self):
        self.change(self.b/'original.json',lambda x:x['rows'][1].update(outcome='skip',detail='original'))
        self.change(self.f/'fixed.json',lambda x:x['rows'][1].update(outcome='skip',detail='different'))
        with self.assertRaises(AssertionError):self.pair()
    def test_reject_regression_error(self):
        self.change(self.b/'baseline-regressions.json',lambda x:x['rows'][-1].update(outcome='error'))
        with self.assertRaises(AssertionError):self.pair()
    def test_reject_missing_expected_failure(self):
        self.change(self.b/'baseline-regressions.json',lambda x:x['rows'][-1].update(outcome='pass'))
        with self.assertRaises(AssertionError):self.pair()
    def test_bun_actual_format_controls(self):
        p=self.root/'bun.log';p.write_text('tests/fixture.test.ts:\n(pass) literal name [1.23ms]\n(skip) unchanged reason\n 1 pass\n 0 fail\n 1 skip\nRan 2 tests across 1 files.\n')
        expected=compare.bun_cases(self.root,'bun')
        p.write_text('tests/fixture.test.ts:\n(pass) literal name [9.01ms]\n(skip) unchanged reason\n 1 pass\n 0 fail\n 1 skip\nRan 2 tests across 1 files.\n')
        self.assertEqual(compare.bun_cases(self.root,'bun'),expected)
        for text in ['(pass) no file\n','tests/fixture.test.ts:\n(fail) literal name [1.23ms]\n','plain PASS\n','tests/fixture.test.ts:\n(pass) duplicate\n(pass) duplicate\n']:
            with self.subTest(text=text):
                p.write_text(text)
                with self.assertRaises(AssertionError):compare.bun_cases(self.root,'bun')
    def test_reject_raw_report_hash_mismatch(self):
        self.pair()
        (self.f/'fixed.json').write_text('{}')
        with self.assertRaises(AssertionError):compare.inspect(self.f,'fixed','python-3.12')
    def test_reject_parent_pass_subtest_fail(self):
        self.change(self.f/'fixed.json',lambda x:x['rows'][-1].update(outcome='fail'))
        with self.assertRaises(AssertionError):self.pair()
    def test_reject_unknown_or_wrong_subtest_parent(self):
        original=(self.f/'fixed.json').read_bytes()
        for parent in [self.old,'tests.unknown.Case.test_unknown']:
            with self.subTest(parent=parent):
                (self.f/'fixed.json').write_bytes(original);self.change(self.f/'fixed.json',lambda x:x['rows'][-1].update(parent=parent))
                with self.assertRaises(AssertionError):self.pair()
    def test_reject_non_utc_and_naive_timestamps(self):
        original=(self.f/'native.json').read_bytes()
        for start,end in [('2026-10-13T00:00:00','2026-10-13T00:00:01'),('2026-10-13T01:00:00+01:00','2026-10-13T01:00:01+01:00')]:
            with self.subTest(start=start):
                (self.f/'native.json').write_bytes(original);self.change(self.f/'native.json',lambda x:x['commands'][0].update(start=start,end=end))
                with self.assertRaises(AssertionError):self.pair()
    def test_reject_noncanonical_argv_and_cwd(self):
        original=(self.f/'native.json').read_bytes()
        for index,change in [(0,{'argv':['python','--help']}),(1,{'argv':['python','-m','pip','install','different']}),(2,{'cwd':'/other-source'}),(2,{'argv':['python','-m','unittest','tests.test_rank_state','-v']})]:
            with self.subTest(index=index,change=change):
                (self.f/'native.json').write_bytes(original);self.change(self.f/'native.json',lambda x:x['commands'][index].update(change))
                with self.assertRaises(AssertionError):self.pair()
    def test_actual_bun122_golden_inventory(self):
        p=self.root/'actual.log';p.write_text(ACTUAL_BUN_FIXED_46)
        cases=compare.bun_cases(self.root,'actual');self.assertEqual(len(cases),46)
        self.assertEqual({name for file,name,outcome in cases},set(ACTUAL_BUN_40_ORIGINAL+ACTUAL_BUN_6_NEW))
        # Dropping a case while retaining the native summary MUST fail.
        p.write_text('\n'.join(line for line in ACTUAL_BUN_FIXED_46.splitlines() if 'extracts date from the listdate <time> element' not in line))
        with self.assertRaises(AssertionError):compare.bun_cases(self.root,'actual')
    def test_reject_paired_runtime_identity_changes(self):
        original=(self.f/'native.json').read_bytes()
        for change in [lambda x:x.update(python='different'),lambda x:x['platform'].update(machine='aarch64')]:
            with self.subTest(change=repr(change)):
                (self.f/'native.json').write_bytes(original);self.change(self.f/'native.json',change)
                with self.assertRaises(AssertionError):self.pair()
        (self.f/'native.json').write_bytes(original)
        (self.f/'runtime.log').write_bytes(b'different runtime')
        self.change(self.f/'native.json',lambda x:x['commands'][0].update(sha256=compare.sha(b'different runtime')))
        with self.assertRaises(AssertionError):self.pair()
    def test_latex_canonical_version_commands(self):
        for lane in ['latex-latest','latex-bookworm']:
            labels=compare.labels(lane,'fixed')
            for tool in ['lualatex','xelatex','pdfinfo','pdftotext']:
                self.assertIn(tool+'-version',labels)
                expected=[tool,'--version' if tool in ['lualatex','xelatex'] else '-v']
                self.assertEqual(compare.command(lane,tool+'-version','/source','python'),(expected,'/source'))
    def latex_pair_fixture(self):
        for path,phase in [(self.b,'baseline'),(self.f,'fixed')]:
            x=json.loads((path/'native.json').read_text());x['lane']='latex-bookworm';x['proof_root']='/proof/latex-bookworm-'+phase;x['container']=compare.M['containers']['latex-bookworm'];x['bootstrap']={'log':'container-bootstrap.log','sha256':compare.sha(b'CONTAINER_BOOTSTRAP_PASS\n')};(path/'container-bootstrap.log').write_bytes(b'CONTAINER_BOOTSTRAP_PASS\n')
            commands=[]
            for label in compare.labels('latex-bookworm',phase):
                argv,cwd=compare.command('latex-bookworm',label,'/source','python');raw=b'same paired version' if label.endswith('-version') else b'pass';(path/(label+'.log')).write_bytes(raw)
                commands.append({'argv':argv,'cwd':cwd,'label':label,'start':'2026-10-13T00:00:00+00:00','end':'2026-10-13T00:00:01+00:00','exit':0,'log':label+'.log','sha256':compare.sha(raw)})
            x['commands']=commands;self.write(path/'native.json',x)
    def test_positive_whole_latex_pair(self):
        self.latex_pair_fixture();self.assertGreater(self.pair_latex()['canonical_commands_fixed'],10)
    def pair_latex(self):
        for path in [self.b,self.f]:
            x=json.loads((path/'native.json').read_text());x['reports']={p.name:compare.sha(p.read_bytes()) for p in path.glob('*.json') if p.name!='native.json'};self.write(path/'native.json',x)
        return compare.pair(self.b,self.f,'latex-bookworm')
    def test_reject_actual_paired_latex_version_differences(self):
        for tool in ['lualatex','xelatex','pdfinfo','pdftotext']:
            with self.subTest(tool=tool):
                self.latex_pair_fixture();label=tool+'-version';(self.f/(label+'.log')).write_bytes(b'different actual version')
                self.change(self.f/'native.json',lambda x:[c.update(sha256=compare.sha(b'different actual version')) for c in x['commands'] if c['label']==label])
                with self.assertRaises(AssertionError):self.pair_latex()
    def network_fixture(self):
        return {'status':'PASS','command':['bun','test'],'cwd':'/source/cli','links':[{'ifname':'lo'}],'routes':[{'dev':'lo','type':'local'}],'ipv6_routes':[{'dev':'lo','type':'local','dst':'::1'}],'loopback':'PASS','external_documentation_address':'203.0.113.1','external_errno':101,'external_result':'ENETUNREACH','external_ipv6_documentation_address':'2001:db8::1','external_ipv6_errno':101,'external_ipv6_result':'ENETUNREACH','parent_net_namespace':'net:[1]','net_namespace':'net:[2]','pid':1,'environment':{'PATH':'/usr/bin'},'uid':0,'gid':0,'executables':{tool:'/usr/bin/'+tool for tool in ['bun','ip','unshare','sudo']},'versions':{tool:'actual-native-placeholder-in-SYNTHETIC-control' for tool in ['unshare','ip','sudo']}}
    def test_positive_network_boundary_receipt(self):compare.inspect_network(self.network_fixture(),'/source/cli','net:[1]')
    def test_network_boundary_fail_closed(self):
        mutations=[lambda x:x['links'].append({'ifname':'eth0'}),lambda x:x['routes'].append({'dev':'eth0','type':'unicast','dst':'default'}),lambda x:x.update(net_namespace='net:[1]'),lambda x:x.update(parent_net_namespace='net:[other]'),lambda x:x.update(loopback='FAIL'),lambda x:x.update(external_errno=110),lambda x:x.update(external_ipv6_errno=110),lambda x:x.update(external_result='connected'),lambda x:x.update(external_ipv6_documentation_address='actual-portal'),lambda x:x.update(command=['bun','test','--filter','subset']),lambda x:x.update(cwd='/other'),lambda x:x['executables'].update(bun='relative-bun')]
        for index,mutation in enumerate(mutations):
            with self.subTest(index=index):
                x=self.network_fixture();mutation(x)
                with self.assertRaises(AssertionError):compare.inspect_network(x,'/source/cli','net:[1]')
    def test_all_six_inner_bun_commands_are_namespaced(self):
        count=0
        for i,cli in enumerate(compare.M['bun_clis']):
            if cli['tests']:
                argv,cwd=compare.command('bun','bun-test-'+str(i),'/source','python','/harness/qualification','/proof','net:[1]');self.assertEqual(argv[:5],['sudo','-n','--preserve-env=PATH','unshare','--net']);self.assertEqual(argv[-3:],['--','bun','test']);self.assertIn('/harness/qualification/network_namespace.py',argv);count+=1
        self.assertGreater(count,0)
    def bun_pair_fixture(self):
        for path,phase in [(self.b,'baseline'),(self.f,'fixed')]:
            x=json.loads((path/'native.json').read_text());x['lane']='bun';x['proof_root']='/proof/bun-'+phase
            commands=[]
            for label in compare.labels('bun',phase):
                argv,cwd=compare.command('bun',label,'/source','python','/harness/qualification',x['proof_root'],'net:[1]')
                raw=b'1.2.22\n' if label=='bun-runtime' else b'pass'
                if label.startswith('bun-test-'):
                    raw=b'tests/example.test.ts:\n(pass) stable fixture [0.1ms]\n 1 pass\n 0 fail\nRan 1 tests across 1 files.\n'
                    proof=self.network_fixture();proof['cwd']=cwd;self.write(path/(label+'-network.json'),proof)
                (path/(label+'.log')).write_bytes(raw)
                commands.append({'argv':argv,'cwd':cwd,'label':label,'start':'2026-10-13T00:00:00+00:00','end':'2026-10-13T00:00:01+00:00','exit':0,'log':label+'.log','sha256':compare.sha(raw)})
            x['commands']=commands;self.write(path/'native.json',x)
    def pair_bun(self):
        for path in [self.b,self.f]:
            x=json.loads((path/'native.json').read_text());x['reports']={p.name:compare.sha(p.read_bytes()) for p in path.glob('*.json') if p.name!='native.json'};self.write(path/'native.json',x)
        return compare.pair(self.b,self.f,'bun')
    def test_relocated_whole_bun_pair(self):
        self.bun_pair_fixture();result=self.pair_bun();self.assertGreater(result['canonical_commands_fixed'],10)
        self.assertNotEqual(str(self.f),'/proof/bun-fixed')
    def test_reject_wrong_recorded_proof_origin(self):
        self.bun_pair_fixture();self.change(self.f/'native.json',lambda x:x.update(proof_root='/raw/bun-fixed'))
        with self.assertRaises(AssertionError):self.pair_bun()
    def test_reject_wrong_recorded_helper_layout(self):
        self.bun_pair_fixture();self.change(self.f/'native.json',lambda x:x.update(helper_root='/other/qualification'))
        with self.assertRaises(AssertionError):self.pair_bun()
ACTUAL_BUN_FIXED_46="\ntests/description-layout.test.ts:\n(pass) LinkedIn detail description layout > documented detail CLI preserves real posting paragraphs in json [42.86ms]\n(pass) LinkedIn detail description layout > documented detail CLI preserves real posting paragraphs in plain [30.73ms]\n(pass) LinkedIn detail description layout > captured description keeps list-item boundaries rather than flattening requirements [0.73ms]\n(pass) LinkedIn detail description layout > captured title and company metadata retain their single-line normalization [0.21ms]\n(pass) LinkedIn detail description layout > source line wrapping and CRLF inside one paragraph remain inline whitespace\n(pass) LinkedIn detail description layout > inline named and numeric entities still decode without creating paragraph breaks [0.34ms]\n\ntests/parsing.test.ts:\n(pass) parseJobCards contract fields > extracts date from the listdate <time> element [0.38ms]\n(pass) parseJobCards contract fields > extracts date from the listdate--new variant class [0.03ms]\n(pass) parseJobCards contract fields > extracts location from the location span\n(pass) parseJobCards contract fields > date and location are null when the elements are absent [0.28ms]\n(pass) decodeHtmlEntities (via parseJobCards) > decodes hexadecimal numeric entities (&#xE9;) [0.08ms]\n(pass) decodeHtmlEntities (via parseJobCards) > decodes uppercase-X hexadecimal entities (&#X...;)\n(pass) decodeHtmlEntities (via parseJobCards) > still decodes decimal numeric entities (&#233;) — regression [0.06ms]\n(pass) decodeHtmlEntities (via parseJobCards) > decodes supplementary-plane code points with fromCodePoint (&#128512;) [0.01ms]\n(pass) decodeHtmlEntities (via parseJobCards) > decodes hex supplementary-plane code points (&#x1F600;)\n(pass) decodeHtmlEntities (via parseJobCards) > decodes hex entities in the company subtitle too [0.03ms]\n(pass) parseJobDetail active-status detection > a closed posting's top-card banner yields isActive: false [0.04ms]\n(pass) parseJobDetail active-status detection > an open posting yields isActive: true [0.01ms]\n(pass) parseJobDetail active-status detection > recruiter boilerplate in the description does not flag a live posting [0.02ms]\n(pass) parseJobDetail active-status detection > a closed-job class named in the description does not flag a live posting [0.01ms]\n(pass) parseJobDetail dropped fields > emits no applyUrl field\n(pass) decodeHtmlEntities (via parseJobDetail) > decodes hex entities inside the job title\n(pass) extractDivContent > extracts content from simple div\n(pass) extractDivContent > extracts content with nested divs — the regression case\n(pass) extractDivContent > returns null when class not found [0.03ms]\n(pass) extractDivContent > works with show-more-less-html__markup class [0.02ms]\n(pass) extractDivContent > handles deeply nested divs (3 levels) [0.02ms]\n(pass) extractDivContent > handles empty content [0.02ms]\n(pass) extractDivContent > parseJobDetail uses extractDivContent and preserves full description [0.04ms]\n(pass) minutesToTPR > converts minutes to an f_TPR seconds window [0.03ms]\n(pass) minutesToTPR > returns null for non-positive input\n(pass) normalizeId > extracts ID from raw numeric string [0.08ms]\n(pass) normalizeId > extracts ID from URN [0.01ms]\n(pass) normalizeId > extracts ID from simple job view URL without trailing slash [0.05ms]\n(pass) normalizeId > extracts ID from simple job view URL with trailing slash [0.02ms]\n(pass) normalizeId > extracts ID from simple job view URL with query parameter [0.01ms]\n(pass) normalizeId > extracts ID from simple job view URL with trailing slash and query parameter\n(pass) normalizeId > extracts ID from slug URL without trailing slash\n(pass) normalizeId > extracts ID from slug URL with trailing slash\n(pass) normalizeId > extracts ID from slug URL with trailing slash and tracking query params\n(pass) normalizeId > extracts ID from regional subdomain LinkedIn URL with trailing slash\n(pass) normalizeId > accepts a scheme-less linkedin.com job URL and a bare title slug [0.03ms]\n(pass) normalizeId > rejects a job URL on any other host instead of extracting its digits [0.02ms]\n(pass) normalizeId > rejects look-alike and userinfo hosts\n(pass) normalizeId > rejects a linkedin.com URL that is not a job view\n(pass) normalizeId > returns null for non-job URLs and invalid strings [0.01ms]\n\n 46 pass\n 0 fail\n 70 expect() calls\nRan 46 tests across 2 files. [202.00ms]\n"
ACTUAL_BUN_40_ORIGINAL=['parseJobCards contract fields > extracts date from the listdate <time> element', 'parseJobCards contract fields > extracts date from the listdate--new variant class', 'parseJobCards contract fields > extracts location from the location span', 'parseJobCards contract fields > date and location are null when the elements are absent', 'decodeHtmlEntities (via parseJobCards) > decodes hexadecimal numeric entities (&#xE9;)', 'decodeHtmlEntities (via parseJobCards) > decodes uppercase-X hexadecimal entities (&#X...;)', 'decodeHtmlEntities (via parseJobCards) > still decodes decimal numeric entities (&#233;) — regression', 'decodeHtmlEntities (via parseJobCards) > decodes supplementary-plane code points with fromCodePoint (&#128512;)', 'decodeHtmlEntities (via parseJobCards) > decodes hex supplementary-plane code points (&#x1F600;)', 'decodeHtmlEntities (via parseJobCards) > decodes hex entities in the company subtitle too', "parseJobDetail active-status detection > a closed posting's top-card banner yields isActive: false", 'parseJobDetail active-status detection > an open posting yields isActive: true', 'parseJobDetail active-status detection > recruiter boilerplate in the description does not flag a live posting', 'parseJobDetail active-status detection > a closed-job class named in the description does not flag a live posting', 'parseJobDetail dropped fields > emits no applyUrl field', 'decodeHtmlEntities (via parseJobDetail) > decodes hex entities inside the job title', 'extractDivContent > extracts content from simple div', 'extractDivContent > extracts content with nested divs — the regression case', 'extractDivContent > returns null when class not found', 'extractDivContent > works with show-more-less-html__markup class', 'extractDivContent > handles deeply nested divs (3 levels)', 'extractDivContent > handles empty content', 'extractDivContent > parseJobDetail uses extractDivContent and preserves full description', 'minutesToTPR > converts minutes to an f_TPR seconds window', 'minutesToTPR > returns null for non-positive input', 'normalizeId > extracts ID from raw numeric string', 'normalizeId > extracts ID from URN', 'normalizeId > extracts ID from simple job view URL without trailing slash', 'normalizeId > extracts ID from simple job view URL with trailing slash', 'normalizeId > extracts ID from simple job view URL with query parameter', 'normalizeId > extracts ID from simple job view URL with trailing slash and query parameter', 'normalizeId > extracts ID from slug URL without trailing slash', 'normalizeId > extracts ID from slug URL with trailing slash', 'normalizeId > extracts ID from slug URL with trailing slash and tracking query params', 'normalizeId > extracts ID from regional subdomain LinkedIn URL with trailing slash', 'normalizeId > accepts a scheme-less linkedin.com job URL and a bare title slug', 'normalizeId > rejects a job URL on any other host instead of extracting its digits', 'normalizeId > rejects look-alike and userinfo hosts', 'normalizeId > rejects a linkedin.com URL that is not a job view', 'normalizeId > returns null for non-job URLs and invalid strings']
ACTUAL_BUN_6_NEW=['LinkedIn detail description layout > documented detail CLI preserves real posting paragraphs in json', 'LinkedIn detail description layout > documented detail CLI preserves real posting paragraphs in plain', 'LinkedIn detail description layout > captured description keeps list-item boundaries rather than flattening requirements', 'LinkedIn detail description layout > captured title and company metadata retain their single-line normalization', 'LinkedIn detail description layout > source line wrapping and CRLF inside one paragraph remain inline whitespace', 'LinkedIn detail description layout > inline named and numeric entities still decode without creating paragraph breaks']
if __name__=='__main__':unittest.main()
