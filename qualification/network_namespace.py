"""Run canonical Bun suite inside inherited, loopback-only Linux network namespace."""
import argparse,errno,json,os,shutil,pathlib,socket,subprocess,sys,threading
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--proof',required=True);p.add_argument('--cwd',required=True);p.add_argument('--parent-netns',required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();assert a.command==['--','bun','test'];assert sys.platform.startswith('linux')
# Linux net namespaces isolate ALL descendants, including original Bun.spawn helpers.
subprocess.run(['ip','link','set','lo','up'],check=True)
def capture(argv):return subprocess.check_output(argv,text=True,stderr=subprocess.STDOUT)
links=json.loads(capture(['ip','-j','link','show']));assert {r['ifname'] for r in links}=={'lo'}
routes=json.loads(capture(['ip','-j','route','show','table','all']));assert all(r.get('dev')=='lo' and r.get('type') in {'local','broadcast'} for r in routes)
routes6=json.loads(capture(['ip','-6','-j','route','show','table','all']));assert all(r.get('dev')=='lo' and r.get('type') in {'local','multicast','unicast'} and r.get('dst') in {'::1','ff00::/8'} for r in routes6)
# Verify working fixture/localserver loopback with literal private test data.
server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1);port=server.getsockname()[1];errors=[]
def serve():
    try:
        server.settimeout(2);conn,_=server.accept()
        with conn:assert conn.recv(32)==b'qualification-loopback';conn.sendall(b'loopback-pass')
    except BaseException as error:errors.append(repr(error))
thread=threading.Thread(target=serve);thread.start()
with socket.create_connection(('127.0.0.1',port),timeout=2) as conn:conn.sendall(b'qualification-loopback');assert conn.recv(32)==b'loopback-pass'
thread.join(3);server.close();assert not thread.is_alive() and not errors
# RFC5737 documentation address: no packets can leave, require kernel ENETUNREACH.
with socket.socket() as conn:
    conn.settimeout(1)
    try:conn.connect(('203.0.113.1',443))
    except OSError as error:assert error.errno==errno.ENETUNREACH;blocked_errno=error.errno
    else:raise AssertionError('external connectivity unexpectedly available')
with socket.socket(socket.AF_INET6) as conn:
    conn.settimeout(1)
    try:conn.connect(('2001:db8::1',443))
    except OSError as error:assert error.errno==errno.ENETUNREACH;blocked_errno6=error.errno
    else:raise AssertionError('external IPv6 connectivity unexpectedly available')
child_namespace=os.readlink('/proc/self/ns/net');assert child_namespace!=a.parent_netns
proof={'status':'PASS','command':a.command[1:],'cwd':str(P(a.cwd).resolve()),'links':links,'routes':routes,'ipv6_routes':routes6,'loopback':'PASS','external_documentation_address':'203.0.113.1','external_errno':blocked_errno,'external_result':'ENETUNREACH','external_ipv6_documentation_address':'2001:db8::1','external_ipv6_errno':blocked_errno6,'external_ipv6_result':'ENETUNREACH','parent_net_namespace':a.parent_netns,'net_namespace':child_namespace,'environment':{'PATH':os.environ.get('PATH','')},'executables':{tool:shutil.which(tool) for tool in ['bun','ip','unshare','sudo']},'pid':os.getpid(),'uid':os.getuid(),'gid':os.getgid(),'versions':{tool:capture(args) for tool,args in [('unshare',['unshare','--version']),('ip',['ip','-V']),('sudo',['sudo','--version'])]}}
P(a.proof).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
os.chdir(a.cwd)
# Same literal inner argv; no preload/mock/source edit and child namespaces inherited.
os.execvp('bun',a.command[1:])
