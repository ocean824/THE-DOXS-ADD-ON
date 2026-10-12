#!/usr/bin/env python3
"""dox-vault: sync a local folder (Obsidian vault, Office documents) or Microsoft 365 files into the D.O.X Workspace knowledge vault.

Requires Python 3.9+ and no third-party packages. Microsoft 365 mode shells out to the CLI for Microsoft 365 (`m365`),
which must already be installed and signed in (`m365 login`). Credentials never leave your machine except the owner login to your own workspace.

  python dox_vault.py login     --base-url https://your-workspace.example.com
  python dox_vault.py folder    ~/Documents/ObsidianVault --scope shared --prefix obsidian
  python dox_vault.py folder    ~/Documents/Closings/Harbor --scope project --transaction <transaction_id>
  python dox_vault.py m365      --web-url https://contoso.sharepoint.com/sites/ops --folder "Shared Documents/Playbooks" --scope shared --prefix sharepoint
  python dox_vault.py status
"""
import argparse,base64,getpass,hashlib,json,os,subprocess,sys,tempfile,urllib.request,urllib.error,urllib.parse
from pathlib import Path

SUPPORTED={'.md','.markdown','.txt','.csv','.json','.yaml','.yml','.docx','.xlsx','.pptx','.pdf'}
TEXT={'.md','.markdown','.txt','.csv','.json','.yaml','.yml'}
CONFIG=Path.home()/'.dox-vault.json'
BATCH=20

def load_config():
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
def save_config(config):
    CONFIG.write_text(json.dumps(config,indent=2));os.chmod(CONFIG,0o600)
def request(config,method,path,body=None,retry=True):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(config['base_url']+'/api'+path,data=data,method=method,headers={'Content-Type':'application/json','Authorization':'Bearer '+config.get('access_token','')})
    try:
        with urllib.request.urlopen(req,timeout=120) as response:return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        if error.code==401 and retry and config.get('refresh_token'):
            refresh(config);return request(config,method,path,body,retry=False)
        detail=error.read().decode(errors='replace')
        try:detail=json.loads(detail).get('detail',detail)
        except Exception:pass
        sys.exit(f'API error {error.code}: {detail}')
def refresh(config):
    req=urllib.request.Request(config['base_url']+'/api/auth/refresh',data=json.dumps({'refresh_token':config['refresh_token']}).encode(),method='POST',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as response:payload=json.loads(response.read())
    config.update(access_token=payload['access_token'],refresh_token=payload['refresh_token']);save_config(config)
def login(args):
    base=args.base_url.rstrip('/');email=args.email or input('Owner email: ');password=getpass.getpass('Password: ')
    req=urllib.request.Request(base+'/api/auth/login',data=json.dumps({'email':email,'password':password,'client':'desktop'}).encode(),method='POST',headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=60) as response:payload=json.loads(response.read())
    except urllib.error.HTTPError as error:sys.exit(f'Login failed ({error.code}): {error.read().decode(errors="replace")}')
    if payload['user']['role']!='OWNER':sys.exit('Only the workspace owner can sync the knowledge vault.')
    save_config({'base_url':base,'access_token':payload['access_token'],'refresh_token':payload['refresh_token'],'email':email})
    print(f'Signed in as {payload["user"]["name"]} · tokens stored in {CONFIG}')
def encode(path):
    raw=path.read_bytes()
    if path.suffix.lower() in TEXT:return {'content':raw.decode('utf-8-sig',errors='replace'),'encoding':'text'}
    return {'content':base64.b64encode(raw).decode(),'encoding':'base64'}
def collect(root,prefix):
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix.lower() in SUPPORTED and not any(part.startswith('.') for part in path.relative_to(root).parts):
            relative=path.relative_to(root).as_posix();files.append(((prefix.strip('/')+'/' if prefix.strip('/') else '')+relative,path))
    return files
def push(config,files,args,source_label):
    if not files:sys.exit('No supported files found (.md .txt .csv .json .yaml .docx .xlsx .pptx .pdf).')
    print(f'{source_label}: {len(files)} file(s) → {config["base_url"]} [{args.scope}{" · "+args.transaction if args.transaction else ""}]')
    totals={'created':0,'updated':0,'unchanged':0,'deleted':0}
    for start in range(0,len(files),BATCH):
        batch=files[start:start+BATCH]
        body={'items':[{'path':rel,**encode(path)} for rel,path in batch],'scope':args.scope,'transaction_id':args.transaction,'project_type':args.project_type,'tags':args.tag or []}
        result=request(config,'POST','/knowledge/sync',body)
        for key in totals:totals[key]+=result.get(key,0)
        print(f'  {start+len(batch)}/{len(files)} · created {result["created"]} updated {result["updated"]} unchanged {result["unchanged"]}')
    if args.prune:
        remote=request(config,'GET','/knowledge/items');prefix=(args.prefix or '').strip('/')
        local={rel for rel,_ in files};stale=[item['path'] for item in remote if (not prefix or item['path'].startswith(prefix+'/')) and item['path'] not in local]
        for start in range(0,len(stale),400):
            result=request(config,'POST','/knowledge/sync',{'items':[{'path':files[0][0],**encode(files[0][1])}],'scope':args.scope,'transaction_id':args.transaction,'project_type':args.project_type,'deleted_paths':stale[start:start+400]})
            totals['deleted']+=result.get('deleted',0)
    print('Done ·',', '.join(f'{k} {v}' for k,v in totals.items()))
def folder(args):
    config=load_config() or sys.exit('Run `login` first.');root=Path(args.path).expanduser().resolve()
    if not root.is_dir():sys.exit(f'{root} is not a folder')
    push(config,collect(root,args.prefix or root.name),args,f'Folder {root}')
def m365(args):
    config=load_config() or sys.exit('Run `login` first.')
    try:subprocess.run(['m365','status'],check=True,capture_output=True)
    except (FileNotFoundError,subprocess.CalledProcessError):sys.exit('CLI for Microsoft 365 is not installed or not signed in. Install: npm i -g @pnp/cli-microsoft365 · then run: m365 login')
    listing=subprocess.run(['m365','file','list','--webUrl',args.web_url,'--folderUrl',args.folder,'--recursive','--output','json'],capture_output=True,text=True)
    if listing.returncode:sys.exit(f'm365 file list failed: {listing.stderr.strip()}')
    entries=[e for e in json.loads(listing.stdout or '[]') if Path(e.get('name','')).suffix.lower() in SUPPORTED]
    if not entries:sys.exit('No supported Office/PDF/Markdown files in that folder.')
    with tempfile.TemporaryDirectory() as temp:
        files=[]
        for entry in entries:
            relative=entry.get('parentReference',{}).get('path','').split(':',1)[-1].strip('/')
            local=Path(temp)/relative/entry['name'];local.parent.mkdir(parents=True,exist_ok=True)
            result=subprocess.run(['m365','spo','file','get','--webUrl',args.web_url,'--url',urllib.parse.unquote(urllib.parse.urlparse(entry['webUrl']).path),'--asFile','--path',str(local)],capture_output=True,text=True)
            if result.returncode:print(f'  skipped {entry["name"]}: {result.stderr.strip()[:120]}');continue
            files.append(((args.prefix.strip('/')+'/' if args.prefix else '')+(relative+'/' if relative else '')+entry['name'],local))
        push(config,files,args,f'Microsoft 365 {args.web_url}/{args.folder}')
def status(args):
    config=load_config() or sys.exit('Run `login` first.');items=request(config,'GET','/knowledge/items')
    print(f'{config["email"]} @ {config["base_url"]} · {len(items)} knowledge item(s)')
    for item in items[:50]:print(f'  [{item["scope"]:7}] {item["path"]}')
def add_sync_args(parser):
    parser.add_argument('--scope',choices=['shared','project'],default='shared');parser.add_argument('--transaction',help='transaction id for project scope')
    parser.add_argument('--project-type',choices=['Single family','Condominium','Townhouse','Commercial','Land']);parser.add_argument('--prefix',help='vault folder prefix')
    parser.add_argument('--tag',action='append');parser.add_argument('--prune',action='store_true',help='delete vault items under the prefix that no longer exist locally')
def main():
    parser=argparse.ArgumentParser(prog='dox-vault',description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('login');p.add_argument('--base-url',required=True);p.add_argument('--email');p.set_defaults(run=login)
    p=sub.add_parser('folder',help='sync an Obsidian vault or any local folder');p.add_argument('path');add_sync_args(p);p.set_defaults(run=folder)
    p=sub.add_parser('m365',help='sync a SharePoint/OneDrive folder through CLI for Microsoft 365');p.add_argument('--web-url',required=True);p.add_argument('--folder',required=True);add_sync_args(p);p.set_defaults(run=m365)
    p=sub.add_parser('status');p.set_defaults(run=status)
    args=parser.parse_args();args.run(args)
if __name__=='__main__':
    main()
