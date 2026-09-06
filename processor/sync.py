"""Read-only source synchronization. Never writes to the Reference Lab or runs AI."""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from build_review_pack import build,build_review_html
SOURCE='https://mohaned-reel-reference-lab.blsi.chatgpt.site'
SITE=Path('docs'); MAX_SITE=850*1024*1024;FONT=os.environ.get('REVIEW_PACK_FONT','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')

def dump(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def curl(url,path=None,head=False):
 u=urlparse(url)
 if u.scheme!='https' or u.netloc!=urlparse(SOURCE).netloc or not u.path.startswith('/api/references'):raise ValueError('Unexpected source URL')
 args=['curl','--fail','--silent','--show-error','--retry','2','--max-time','180','--max-filesize',str(100*1024*1024)]
 if head:args+=['--head']
 if path:args+=['--output',str(path)]
 return subprocess.run(args+[url],capture_output=True,check=True).stdout

def fingerprint(sha,record):
 return hashlib.sha256(json.dumps([sha,record.get('transcript'),record.get('transcript_segments')],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def size(path):return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.exists() else 0
def complete(target):return all((target/name).exists() for name in ['review.pdf','analysis.json','ai.txt','review.html','frames']) and any((target/'frames').glob('*.jpg'))

def sync(reference_id=None):
 index_path=SITE/'packs.json';index=json.loads(index_path.read_text()) if index_path.exists() else {'schemaVersion':'1.0','references':{}}
 url=SOURCE+('/api/references/'+reference_id if reference_id else '/api/references?limit=100');seen=set();processed=0;failures=0;now=datetime.now(timezone.utc).isoformat();records=[]
 while url:
  if url in seen:raise ValueError('Pagination cycle')
  seen.add(url);data=json.loads(curl(url));url=data.get('next_url') if not reference_id else None
  records.extend(data['references'] if 'references' in data else [data])
 for r in sorted(records,key=lambda r:index['references'].get(r['id'],{}).get('lastAttemptAt','')):
  rid=r['id']
  if not re.fullmatch(r'[a-f0-9-]{36}',rid):raise ValueError('Invalid reference ID')
  if not r.get('video_url') or r.get('preparation_status')!='ready':continue
  target=SITE/'references'/rid;previous=index['references'].get(rid,{})
  try:
   existing=json.loads((target/'analysis.json').read_text()) if (target/'analysis.json').exists() else None
   if existing and not (target/'review.html').exists():
    build_review_html(existing,target)
    print(rid,'backfilled review.html from existing evidence')
   headers=curl(r['video_url'],head=True).decode();match=re.search(r'^etag:\s*(.+)$',headers,re.M|re.I);etag=match.group(1).strip() if match else None
   text_hash=hashlib.sha256(json.dumps([r.get('transcript'),r.get('transcript_segments')],ensure_ascii=False).encode()).hexdigest()
   if previous.get('status')=='Ready' and etag and previous.get('etag')==etag and previous.get('transcriptHash')==text_hash and complete(target):continue
   if processed>=4:continue  # Bound each free run; remaining records are picked up by the next poll.
   processed+=1
   with tempfile.TemporaryDirectory(prefix='reel-') as td:
    temp=Path(td);video=temp/'source.mp4';curl(r['video_url'],video)
    sha=hashlib.sha256(video.read_bytes()).hexdigest();fp=fingerprint(sha,r)
    reused=bool(existing and existing.get('sourceVideoSha256')==sha and existing.get('transcript',{}).get('text')==r.get('transcript') and (existing.get('transcript',{}).get('segments') or None)==(r.get('transcript_segments') or None))
    if not reused:
     output=temp/'pack';build(r,video,output,'ffmpeg','ffprobe',FONT)
     if size(SITE)-size(target)+size(output)>MAX_SITE:raise ValueError('free_storage_limit')
     # Preserve the last published pack until every replacement asset has been generated.
     if target.exists():shutil.rmtree(target)
     shutil.copytree(output,target)
    manifest=json.loads((target/'analysis.json').read_text());build_review_html(manifest,target)
    index['references'][rid]={'status':'Ready','fingerprint':fp,'etag':etag,'transcriptHash':text_hash,'generatedAt':manifest['generatedAt'],'frameCount':len(manifest['frames']),'lastVerifiedAt':now,'sourceVideoSha256':sha,'sourceTranscript':r.get('transcript'),'reusedExistingPack':reused}
    print(rid, 'reused existing pack' if reused else 'generated')
  except Exception as exc:
   failures+=1
   # Do not publish response bodies, input content, or credentials in logs/errors.
   code='free_storage_limit' if str(exc)=='free_storage_limit' else 'generation_failed'
   index['references'][rid]={**previous,'status':'Failed','error':code,'lastAttemptAt':now,'previousPackAvailable':(target/'review.pdf').exists()}
   print(rid,code)
 # A daily factual check report gives visible health information even when no new Reel arrives.
 index['lastSuccessfulPollDate']=now[:10];index['processor']='GitHub Actions standard public runner';index['autoRetry']='Next scheduled poll';dump(index_path,index)
 if size(SITE)>MAX_SITE:raise RuntimeError('Free static capacity limit reached; no paid fallback permitted')
 print(json.dumps({'processed':processed,'failed':failures,'storedPacks':len(index['references'])}))
 return failures
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--reference-id');args=parser.parse_args()
 if args.reference_id and not re.fullmatch(r'[a-f0-9-]{36}',args.reference_id):raise SystemExit('Invalid reference ID')
 raise SystemExit(sync(args.reference_id))
