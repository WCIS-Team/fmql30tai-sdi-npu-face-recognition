from ssh_transport import board_connection,ROOT
import json,shlex
OUT=ROOT/'outputs/incident-20261013'
with board_connection() as c:
 s=c.open_sftp()
 base='/var/log/journal/c18338d14c3049b3ab6cdaed8c0ee749'
 files=sorted([a for a in s.listdir_attr(base) if a.filename.startswith('system')],key=lambda a:a.st_mtime,reverse=True)
 listing=[{'path':base+'/'+a.filename,'size':a.st_size,'mtime':a.st_mtime} for a in files[:8]]
 print('Recent journals:',json.dumps(listing),flush=True)
 (OUT/'recent-journals.json').write_text(json.dumps(listing,indent=2),encoding='utf-8')
 for path in ['/root/funasr/asr/hb.sh','/etc/systemd/journald.conf','/etc/rc.local']:
  try:
   with s.open(path) as f:data=f.read().decode(errors='replace')
   (OUT/(path.rsplit('/',1)[-1]+'.txt')).write_text(data,encoding='utf-8')
   print(path+'\n'+data[:8500],flush=True)
  except OSError as ex:print(path+': '+str(ex),flush=True)
 commands={'recent_files':"find /root -maxdepth 3 -type f -newermt '2026-10-13 10:45:00' -printf '%p %s bytes\\n' | head -60; ps -eo pid,stat,comm | tail -35",'boot_kernel_all':"journalctl -k -b 763f9a31-36a9-4e47-83dd-2ad1b6b661b8 --no-pager -n 230"}
 for idx,a in enumerate(files[:3]):
  commands['journal_tail_'+str(idx)]='journalctl --file='+shlex.quote(base+'/'+a.filename)+' --no-pager -n 100 -o short-iso'
 for name,cmd in commands.items():
  _,o,e=c.exec_command(cmd,timeout=12)
  try:data=o.read().decode(errors='replace')+e.read().decode(errors='replace')
  except Exception as ex:data='Read failure: '+type(ex).__name__
  (OUT/(name+'.txt')).write_text(data,encoding='utf-8')
  print(name+'\n'+data[-12000:],flush=True)
 s.close()
