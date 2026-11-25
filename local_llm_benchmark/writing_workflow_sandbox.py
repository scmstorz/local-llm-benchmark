"""Versioned macOS boundary for the offline writing Pi prototype.

An acceptance run proves only the observed local runtime/profile combination.
No live model authority follows from an offline sandbox acceptance.
"""
from pathlib import Path
import platform
from .macos_sandbox import _literal_rule,_sbpl_string,SEATBELT_EXECUTABLE


def build_profile(root:Path,run:Path,node:Path,gateway_port:int)->str:
    if platform.system()!='Darwin' or platform.machine()!='arm64' or not SEATBELT_EXECUTABLE.is_file():
        raise ValueError('This prototype requires the declared macOS Apple Silicon boundary')
    if type(gateway_port)is not int or not 1<=gateway_port<=65535 or gateway_port==11434:
        raise ValueError('Only an explicit non-Ollama controller port is admitted')
    root=root.resolve();run=run.resolve();node=node.resolve();integration=root/'integrations/pi'
    state=run/'pi-state';workspace=run/'workspace';policy=run/'policy.json'
    readable=[integration,node.parent.parent]
    metadata=set()
    for p in [*readable,state,workspace,policy,node]:metadata.update(p.parents)
    lines=['(version 1)','(deny default)','(allow process-fork)',
      '(allow signal (target same-sandbox))','(allow process-info* (target same-sandbox))',
      _literal_rule('process-exec',[node]),
      '(allow file-read*)',
      '(deny file-read* (subpath "/Users") (subpath "/private/tmp") (subpath "/private/var/folders"))',
      f'(deny file-read* (subpath {_sbpl_string(Path.home())}) (subpath {_sbpl_string(root)}))',
      _literal_rule('file-read-metadata',list(metadata)),
      _literal_rule('file-read*',[node,policy]),
      '(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random") (literal "/private/etc/localtime"))']
    lines.extend(f'(allow file-read* (subpath {_sbpl_string(p)}))' for p in readable)
    lines.extend([f'(allow file-read* (subpath {_sbpl_string(workspace)}))',
      f'(allow file-read* file-write* (subpath {_sbpl_string(state)}))',
      '(allow file-write-data (literal "/dev/null"))','(allow sysctl-read)',
      '(allow iokit-open (iokit-registry-entry-class "RootDomainUserClient"))',
      '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo") (global-name "com.apple.bsd.dirhelper") (global-name "com.apple.system.opendirectoryd.membership") (global-name "com.apple.SystemConfiguration.DNSConfiguration") (global-name "com.apple.SystemConfiguration.configd"))',
      '(allow ipc-posix-sem)',
      '(allow system-socket (require-all (socket-domain AF_SYSTEM) (socket-protocol 2)))',
      f'(allow network-outbound (remote ip "localhost:{gateway_port}"))'])
    return '\n'.join(lines)+'\n'


def command(run:Path,node:Path,*args:str)->list[str]:
    return [str(SEATBELT_EXECUTABLE),'-f',str(run/'sandbox.sb'),str(node),*args]


def acceptance(root: Path, run: Path, node: Path, gateway_url: str, nonce: str, environment: dict) -> dict:
    """Run the twelve OS probes before any model request in this Pi trial."""
    import json
    import subprocess
    from .calibration_run import save
    state=run/'pi-state';state.mkdir(exist_ok=False)
    canary=run/'host-canary';canary.write_text('HOST ONLY\n')
    link=run/'workspace'/'hidden-link';link.symlink_to(canary)
    policy={'root':str(root),'run_root':str(run),'workspace':str(run/'workspace'),
            'gateway':gateway_url,'controller_nonce':nonce}
    code=r'''
const fs=require('fs'),net=require('net'),cp=require('child_process');
const p=JSON.parse(process.argv[1]),checks={},details={};
function allow(n,fn){try{fn();checks[n]=true}catch(e){checks[n]=false;details[n]=e.code||String(e)}}
function deny(n,fn){try{fn();checks[n]=false;details[n]='unexpectedly allowed'}catch(e){checks[n]=['EPERM','EACCES'].includes(e.code);details[n]=e.code||String(e)}}
function socket(n,host,port){return new Promise(resolve=>{const s=net.connect({host,port});const t=setTimeout(()=>{checks[n]=false;details[n]='timeout';s.destroy();resolve()},1000);s.on('connect',()=>{clearTimeout(t);checks[n]=false;details[n]='connected';s.destroy();resolve()});s.on('error',e=>{clearTimeout(t);checks[n]=['EPERM','EACCES'].includes(e.code);details[n]=e.code;resolve()})})}
(async()=>{
allow('candidate_read',()=>fs.readFileSync(p.workspace+'/brief.md'));
allow('own_state_write',()=>fs.writeFileSync(p.run_root+'/pi-state/probe','allowed'));
deny('judge_read_blocked',()=>fs.readFileSync(p.root+'/tasks/workflow-drafts/offline-writing-v0.1/judge/reference.json'));
deny('handoff_read_blocked',()=>fs.readFileSync(p.root+'/SESSION_HANDOFF.md'));
deny('host_read_blocked',()=>fs.readFileSync(p.run_root+'/host-canary'));
deny('symlink_escape_blocked',()=>fs.readFileSync(p.workspace+'/hidden-link'));
deny('candidate_write_blocked',()=>fs.writeFileSync(p.workspace+'/brief.md','MUST NOT WRITE'));
deny('outside_write_blocked',()=>fs.writeFileSync(p.run_root+'/outside-probe','MUST NOT WRITE'));
const shell=cp.spawnSync('/bin/sh',['-c','exit 0']);checks.shell_blocked=!!shell.error&&['EPERM','EACCES'].includes(shell.error.code);
await socket('direct_ollama_socket_blocked','127.0.0.1',11434);
await socket('external_socket_blocked','192.0.2.1',443);
try{const r=await fetch(p.gateway+'/offline-identity',{redirect:'error'});const v=await r.json();checks.controller_allowed=r.ok&&v.controller_nonce===p.controller_nonce}catch(e){checks.controller_allowed=false;details.controller_allowed=String(e)}
console.log(JSON.stringify({checks,details,passed:Object.values(checks).every(Boolean)}));process.exitCode=Object.values(checks).every(Boolean)?0:1;
})().catch(e=>{console.error(e);process.exitCode=2});
'''
    (run/'sandbox-probe.js').write_text(code)
    try:
        result=subprocess.run(command(run,node,'-e',code,json.dumps(policy)),cwd=run/'workspace',
                              env=environment,capture_output=True,text=True,timeout=15)
        (run/'sandbox-probe.stdout').write_text(result.stdout)
        (run/'sandbox-probe.stderr').write_text(result.stderr)
        record=json.loads(result.stdout) if result.returncode==0 else {'passed':False,'returncode':result.returncode}
        save(run/'sandbox-acceptance.json',record)
        if result.returncode or record.get('passed') is not True:
            raise ValueError('Pi OS boundary rejected before any model call')
        return record
    finally:
        link.unlink(missing_ok=True)
        (state/'probe').unlink(missing_ok=True)
        state.rmdir()
