from school_connection import school_connection,ROOT
import json
remote=json.loads((ROOT/'outputs/school_cache.json').read_text())['directory']+'/heartbeat'
assert remote.startswith('/D:/yzd/tmp/wcis-fpga-20261013-')
local=ROOT/'tools/heartbeat'
with school_connection() as c:
 s=c.open_sftp()
 try:s.mkdir(remote)
 except OSError:s.stat(remote)
 for name in ['wcis-heartbeat.c','build-heartbeat.sh']:s.put(str(local/name),remote+'/'+name)
 _,o,e=c.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login '+remote.lstrip('/')+'/build-heartbeat.sh',timeout=60)
 text=o.read().decode(errors='replace')+e.read().decode(errors='replace')
 (ROOT/'outputs/incident-20261013/heartbeat-build.txt').write_text(text,encoding='utf-8')
 print(text)
 if o.channel.recv_exit_status()!=0:raise SystemExit('Build failed')
 s.get(remote+'/wcis-heartbeat',str(local/'wcis-heartbeat'));s.close()
