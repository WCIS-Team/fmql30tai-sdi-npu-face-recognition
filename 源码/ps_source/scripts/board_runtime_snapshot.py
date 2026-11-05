from ssh_transport import board_connection,ROOT
import json
with board_connection() as c:
 cmd="ps -eo pid,etime,pcpu,rss,comm,args | grep -E '[w]cis_sdi|[t]imeout.*wcis'; ls -l /root/bits; find /etc/systemd/system /etc/init.d /etc/rc.local -maxdepth 2 -type f 2>/dev/null | xargs grep -l '/root/bits' 2>/dev/null; dmesg | tail -12"
 _,o,e=c.exec_command(cmd,timeout=30)
 data=o.read().decode(errors='replace')+e.read().decode(errors='replace')
 print(data)
 (ROOT/'outputs/ps_app/board_runtime_snapshot.txt').write_text(data,encoding='utf-8')
