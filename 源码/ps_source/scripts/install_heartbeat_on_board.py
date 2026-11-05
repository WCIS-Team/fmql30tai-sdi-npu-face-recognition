from ssh_transport import board_connection,ROOT
import hashlib,json,shlex,time
folder=ROOT/'tools/heartbeat';out=ROOT/'outputs/incident-20261013'
r={'firmware_changed':False,'visual_application_started':False,'interval_seconds':10,'log_file':'/var/log/wcis-heartbeat/heartbeat.log','school_build_cache':'D:/yzd/tmp/wcis-fpga-20261013-62670b32/heartbeat'}
def run(c,cmd,timeout=15):
 _,o,e=c.exec_command(cmd,timeout=timeout)
 data=o.read().decode(errors='replace')+e.read().decode(errors='replace');rc=o.channel.recv_exit_status()
 if rc:raise RuntimeError(str(rc)+': '+data)
 return data
with board_connection() as c:
 s=c.open_sftp()
 for target in ['/usr/local/libexec','/var/log/wcis-heartbeat']:
  try:s.stat(target)
  except FileNotFoundError:s.mkdir(target)
 s.chmod('/var/log/wcis-heartbeat',0o750)
 for name,target in [('wcis-heartbeat','/usr/local/libexec/wcis-heartbeat'),('wcis-heartbeat.service','/etc/systemd/system/wcis-heartbeat.service')]:
  source=folder/name;sha=hashlib.sha256(source.read_bytes()).hexdigest()
  try:
   with s.open(target) as f:old=hashlib.sha256(f.read()).hexdigest()
   if old!=sha:
    if name=='wcis-heartbeat' and old=='32d2cd11712987cb516786fccd08682118c4aa4526e7101d0956aa2cb06cf1e5':
     s.put(str(source),target)
    else:raise RuntimeError('Existing unrelated file differs: '+target)
  except FileNotFoundError:s.put(str(source),target)
  s.chmod(target,0o755 if name=='wcis-heartbeat' else 0o644)
  assert sha in run(c,'sha256sum '+shlex.quote(target))
  r[name]={'sha256':sha,'path':target,'size_bytes':source.stat().st_size}
 r['self_test']=run(c,'/usr/local/libexec/wcis-heartbeat --self-test')
 r['unit_check']=run(c,'systemd-analyze verify /etc/systemd/system/wcis-heartbeat.service')
 print('Self-test passed and service unit verified.',flush=True)
 run(c,'systemctl daemon-reload && systemctl enable --now wcis-heartbeat.service')
 r['initial_state']=run(c,'systemctl show wcis-heartbeat.service -p ActiveState -p SubState -p MainPID -p MemoryCurrent -p CPUUsageNSec -p NRestarts -p UnitFileState')
 print(r['initial_state'],flush=True)
 r['log_initial']=run(c,'tail -n 4 /var/log/wcis-heartbeat/heartbeat.log')
 assert 'kernel_capture=enabled' in r['log_initial']
 print(r['log_initial'],flush=True)
 r['pid_before_restart']=int(run(c,'systemctl show wcis-heartbeat.service -p MainPID --value').strip())
 run(c,'systemctl kill --kill-who=main --signal=SIGKILL wcis-heartbeat.service')
 print('Testing automatic restart of heartbeat service only.',flush=True)
 time.sleep(12)
 r['pid_after_restart']=int(run(c,'systemctl show wcis-heartbeat.service -p MainPID --value').strip())
 assert r['pid_after_restart']>0 and r['pid_after_restart']!=r['pid_before_restart']
 r['restart_check']=run(c,'systemctl show wcis-heartbeat.service -p ActiveState -p SubState -p NRestarts -p UnitFileState')
 assert 'ActiveState=active' in r['restart_check'] and 'NRestarts=1' in r['restart_check'] and 'UnitFileState=enabled' in r['restart_check']
 pid=r['pid_after_restart']
 r['baseline']=run(c,'cat /proc/'+str(pid)+'/stat; grep -E "VmRSS|VmSize|Threads" /proc/'+str(pid)+'/status; getconf CLK_TCK; cat /proc/uptime')
 time.sleep(21)
 r['after_21_seconds']=run(c,'cat /proc/'+str(pid)+'/stat; grep -E "VmRSS|VmSize|Threads" /proc/'+str(pid)+'/status; getconf CLK_TCK; cat /proc/uptime')
 r['log_verified']=run(c,'tail -n 9 /var/log/wcis-heartbeat/heartbeat.log')
 r['final_service_state']=run(c,'systemctl show wcis-heartbeat.service -p ActiveState -p SubState -p MainPID -p MemoryCurrent -p CPUUsageNSec -p NRestarts -p UnitFileState; du -k /var/log/wcis-heartbeat')
 print(r['final_service_state']+'\n'+r['after_21_seconds']+'\n'+r['log_verified'],flush=True)
 s.close()
(out/'heartbeat-install-verification.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: enabled at boot, auto-restart, metrics and kernel capture. No board reboot performed.',flush=True)
