from ssh_transport import board_connection, ROOT
from pathlib import Path
import json,time
OUT=ROOT/'outputs/incident-20261013';OUT.mkdir(exist_ok=True)
checks={
'state':"date -Is; uptime; cat /proc/sys/kernel/random/boot_id; free -m; ps -eo pid,stat,comm | head -45",
'log_inventory':"find /var/log -maxdepth 2 -type f -printf '%p %s bytes %TY-%Tm-%Td %TH:%TM\\n' | head -100; find /root /opt /usr/local /etc/systemd/system /etc/cron.d -maxdepth 4 \\( -iname '*heartbeat*' -o -iname '*heart*' -o -iname '*watchdog*' -o -iname '*心跳*' -o -iname '*health*' \\) -print 2>/dev/null | head -100",
'boots':"journalctl --list-boots --no-pager; last -x -n 10; ls -la /sys/fs/pstore /var/lib/systemd/pstore 2>/dev/null",
'previous_kernel':"journalctl -k -b -1 --no-pager -n 180",
'current_kernel':"dmesg | tail -90",
'task_logs':"find /root/wcis-vision/20261013-ea8135622061/logs -maxdepth 2 -type f -printf '%p %s bytes\\n'; systemctl list-units --all --no-pager --plain | grep -Ei 'heart|watch|health|monitor'; ls -lt /root | head -30"
}
results={}
with board_connection() as c:
 for name,cmd in checks.items():
  _,o,e=c.exec_command(cmd,timeout=15)
  try:
   data=o.read().decode(errors='replace')+e.read().decode(errors='replace');rc=o.channel.recv_exit_status()
  except Exception as ex:data=type(ex).__name__;rc=None
  results[name]={'exit_code':rc,'output':data}
  (OUT/(name+'.txt')).write_text(data,encoding='utf-8')
  print(name+'\n'+data,flush=True)
(OUT/'initial-read.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
