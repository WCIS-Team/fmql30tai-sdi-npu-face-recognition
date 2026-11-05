from ssh_transport import board_connection,ROOT
import json
with board_connection() as c:
 cmd="pid=$(systemctl show wcis-heartbeat.service -p MainPID --value); grep -E 'Rss:|Pss:|Private|Shared' /proc/$pid/smaps_rollup; systemctl is-enabled wcis-heartbeat.service; systemctl is-active wcis-heartbeat.service; ls -l /etc/systemd/system/multi-user.target.wants/wcis-heartbeat.service; tail -n 3 /var/log/wcis-heartbeat/heartbeat.log; journalctl --file=/var/log/journal/c18338d14c3049b3ab6cdaed8c0ee749/system.journal --no-pager -g 'file.*error|omfile|Read.only|permission' -n 8"
 _,o,e=c.exec_command(cmd,timeout=15);data=o.read().decode(errors='replace')+e.read().decode(errors='replace')
 print(data);(ROOT/'outputs/incident-20261013/heartbeat-final-check.txt').write_text(data,encoding='utf-8')
 # Flush only the newly installed heartbeat files and their parent directories.
 code="import os; paths=['/usr/local/libexec/wcis-heartbeat','/etc/systemd/system/wcis-heartbeat.service','/usr/local/libexec','/etc/systemd/system','/etc/systemd/system/multi-user.target.wants','/var/log/wcis-heartbeat','/var/log']; [(lambda f: (os.fsync(f),os.close(f)))(os.open(p,os.O_RDONLY)) for p in paths]; print('Heartbeat files and directory entries synced')"
 import shlex
 _,o,e=c.exec_command('python3 -c '+shlex.quote(code),timeout=15);print(o.read().decode()+e.read().decode())
r=json.loads((ROOT/'outputs/incident-20261013/heartbeat-install-verification.json').read_text())
def cpu_stat(text):
 lines=text.splitlines();fields=lines[0][lines[0].rfind(')')+2:].split();ticks=int(fields[11])+int(fields[12]);up=float(lines[-1].split()[0]);return ticks,up
before,up1=cpu_stat(r['baseline']);after,up2=cpu_stat(r['after_21_seconds'])
print('CPU seconds:',(after-before)/100,'over wall seconds:',up2-up1,'one-core percent:',100*((after-before)/100)/(up2-up1))
