from ssh_transport import board_connection,ROOT
import json
checks={
'heartbeat_files':"ls -lah /root/hb; find /root/hb -maxdepth 2 -type f -printf '%p %s bytes %TY-%Tm-%Td %TH:%TM\\n'; ls -ld /root/wcis* /root/pkg39 2>/dev/null; findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS | head -6; ls -l /etc/systemd/system/*hb* /usr/local/bin/*hb* /root/*hb* 2>/dev/null",
'heartbeat_tails':"find /root/hb -maxdepth 1 -type f \\( -iname '*.log' -o -iname '*.csv' -o -iname '*.jsonl' -o -iname '*.txt' \\) -print -exec tail -n 35 {} \\;",
'journal_files':"find /var/log/journal -maxdepth 2 -type f -printf '%p %s bytes %TY-%Tm-%Td %TH:%TM\\n'; ls -la /sys/fs/pstore; cat /root/net-boot.log | tail -35; last -x -n 12",
'monitor_sources':"grep -rilE '(/root/hb|heartbeat)' /etc/systemd/system /etc/cron.d /etc/rc.local /usr/local/bin 2>/dev/null | head -25; ps -eo pid,stat,comm | grep -Ei 'python|hb|heart|wcis|timeout'"
}
r={}
with board_connection() as c:
 for name,cmd in checks.items():
  _,o,e=c.exec_command(cmd,timeout=15)
  data=o.read().decode(errors='replace')+e.read().decode(errors='replace');rc=o.channel.recv_exit_status()
  r[name]={'exit_code':rc,'output':data};(ROOT/'outputs/incident-20261013'/ (name+'.txt')).write_text(data,encoding='utf-8')
  print(name+'\n'+data,flush=True)
(ROOT/'outputs/incident-20261013/heartbeat-read.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
