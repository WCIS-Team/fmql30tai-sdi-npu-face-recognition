from ssh_transport import board_connection,ROOT
from pathlib import Path
OUT=ROOT/'outputs/incident-20261013'
base='/var/log/journal/c18338d14c3049b3ab6cdaed8c0ee749/system.journal'
checks={
'journal_boot_ids':'journalctl --file='+base+' -F _BOOT_ID --no-pager',
'incident_window':'journalctl --file='+base+" --since '2026-10-13 10:45:00' --until '2026-10-13 11:17:00' --no-pager -o short-iso -n 160",
'error_signatures':'journalctl --file='+base+" --no-pager -o short-iso -g 'Out of memory|oom-kill|Killed process|soft lockup|hard LOCKUP|blocked for more|Call trace|SError|Unhandled fault|Oops|watchdog|I/O error|mmc.*error|Cannot open|Permission denied|Read-only file system' -n 100",
'root_storage':'df -h / /var/log; cat /proc/mounts | head -5; ls -ld /var/log /var/log/syslog /var/log/kern.log /var/log/auth.log; ls -l /var/log/journal/c18338d14c3049b3ab6cdaed8c0ee749/system.journal; cat /sys/block/mmcblk0/ro',
'heartbeat_recent':"find /tmp /run /home -maxdepth 3 \\( -iname '*hb*.log' -o -iname '*heartbeat*' -o -iname '*heart*.log' \\) -printf '%p %TY-%Tm-%Td %TH:%TM\\n' 2>/dev/null | head -35"
}
with board_connection() as c:
 for name,cmd in checks.items():
  _,o,e=c.exec_command(cmd,timeout=15)
  try:data=o.read().decode(errors='replace')+e.read().decode(errors='replace')
  except Exception as ex:data='Read failure: '+type(ex).__name__
  (OUT/(name+'.txt')).write_text(data,encoding='utf-8');print(name+'\n'+data,flush=True)
 s=c.open_sftp()
 for remote,local in [('/root/plin_demo/PLin+SingleNet+HDMI/src/sdicamera+yolov5+hdmi.cpp','board-reference.cpp'),('/root/plin_demo/PLin+SingleNet+HDMI/CMakeLists.txt','board-reference-CMakeLists.txt')]:
  s.get(remote,str(OUT/local))
 s.close()
