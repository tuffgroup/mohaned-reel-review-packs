"""Exercise the permanent pipeline with temporary synthetic media, never saved Reels."""
import contextlib,copy,io,json,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'processor')
import sync
from PIL import Image

def main():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);source=root/'input.mp4'
  def video(color):subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=c={color}:s=320x180:r=24:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
  video('blue');rid='11111111-1111-4111-8111-111111111111'
  record={'id':rid,'detail_url':sync.SOURCE+'/references/'+rid,'original_instagram_url':None,'video_url':sync.SOURCE+'/api/references/'+rid+'/video','preparation_status':'ready','internal_title':'Synthetic test','creator':None,'caption':'Exact caption\nSecond line.','transcript':'Exact transcript\nSecond line.'}
  etag=['"version1"'];downloads=[]
  def fetch(url,path=None,head=False):
   if head:return ('HTTP/2 200\netag: '+etag[0]+'\n').encode()
   if path:Path(path).write_bytes(source.read_bytes());downloads.append(url);return b''
   return json.dumps({'references':[copy.deepcopy(record)],'next_url':None}).encode()
  with patch.object(sync,'SITE',root/'docs'),patch.object(sync,'curl',fetch),contextlib.redirect_stdout(io.StringIO()):
   assert sync.sync()==0
   pack=root/'docs/references'/rid;manifest=json.loads((pack/'analysis.json').read_text())
   assert len(manifest['frames'])==8
   assert manifest['transcript']['text']==record['transcript'] and manifest['caption']==record['caption']
   assert manifest['transcript']['segments'] is None
   assert all(f['transcriptSegment'] is None for f in manifest['frames'])
   assert (pack/'review.pdf').read_bytes().startswith(b'%PDF')
   with Image.open(pack/'frames/000000.jpg') as im:assert im.size==(720,406)
   initial=(pack/'review.pdf').read_bytes();downloads.clear();assert sync.sync()==0 and not downloads
   assert (pack/'review.pdf').read_bytes()==initial
   record['internal_title']='Metadata-only change';assert sync.sync()==0 and not downloads
   record['transcript']='Changed transcript exactly.';assert sync.sync()==0 and len(downloads)==1
   assert json.loads((pack/'analysis.json').read_text())['transcript']['text']==record['transcript']
   video('red');etag[0]='"version2"';assert sync.sync()==0
   assert json.loads((pack/'analysis.json').read_text())['sourceVideoSha256']!=manifest['sourceVideoSha256']
   current=(pack/'review.pdf').read_bytes();record['transcript']='Failing replacement.'
   with patch.object(sync,'MAX_SITE',1):
    try:sync.sync()
    except RuntimeError:pass
   assert (pack/'review.pdf').read_bytes()==current and source.exists()
   state=json.loads((root/'docs/packs.json').read_text());assert state['references'][rid]['status']=='Failed'
 print('PASS: new video, unchanged skip, metadata-only skip, transcript change, video replacement, failure preservation, timing honesty, real JPEG/PDF generation')
if __name__=='__main__':main()
