"""Build stored evidence derivatives from a reference record and its original MP4.
No AI calls; no source writes. Requires ffmpeg, ffprobe, reportlab and Pillow.
"""
import argparse,bisect,hashlib,json,math,re,subprocess,tempfile
from pathlib import Path
from datetime import datetime,timezone
from xml.sax.saxutils import escape
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader

VERSION='1.0'
def command(args):
    return subprocess.run(args,capture_output=True,text=True,check=True).stdout

def timestamps(duration):
    result=[]
    for start,end,step in [(0,min(5,duration),.25),(5,min(15,duration),.5),(15,duration,1)]:
        n=0
        while start+n*step<end-1e-6:
            result.append(round(start+n*step,6));n+=1
    return result

def label(seconds):
    whole=int(seconds);return f'{whole//60:02d}:{seconds%60:06.3f}'

def segment_at(segments,t):
    if not segments:return None
    hits=[s for s in segments if s['start']<=t<s['end']]
    return ' '.join(s['text'] for s in hits) if hits else None

def source_segments(record):
    # Only copy real timings supplied by the stored record. Never estimate word timings.
    candidates=record.get('transcript_segments')
    if not candidates and isinstance(record.get('transcript'),dict):candidates=record['transcript'].get('segments')
    if not candidates:return None
    result=[]
    for s in candidates:
        if isinstance(s.get('start'),(int,float)) and isinstance(s.get('end'),(int,float)) and s['end']>=s['start'] and isinstance(s.get('text'),str):
            result.append({'start':s['start'],'end':s['end'],'text':s['text'],'timing':s.get('timing','source_segment')})
    return result or None

def build(record,video,out,ffmpeg,ffprobe,font):
    out.mkdir(parents=True,exist_ok=True);(out/'frames').mkdir(exist_ok=True)
    probe=json.loads(command([ffprobe,'-v','error','-select_streams','v:0','-show_streams','-show_format','-of','json',str(video)]))
    stream=probe['streams'][0];duration=float(stream.get('duration') or probe['format']['duration'])
    if duration<=0 or not math.isfinite(duration):raise ValueError('Invalid video duration')
    timing=json.loads(command([ffprobe,'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)]))
    pts=[float(x['best_effort_timestamp_time']) for x in timing['frames'] if 'best_effort_timestamp_time' in x]
    if not pts:raise ValueError('No video frames decoded')
    start_pts=pts[0];pts=[round(t-start_pts,6) for t in pts]
    scene_run=subprocess.run([ffmpeg,'-hide_banner','-nostdin','-i',str(video),'-an','-vf',"scale=320:-2,select='gt(scene,0.30)',showinfo",'-vsync','0','-f','null','-'],capture_output=True,text=True,check=True)
    scene_pts=[round(float(t)-start_pts,6) for t in re.findall(r'pts_time:([0-9.]+)',scene_run.stderr)]
    def nearest(t):
        i=bisect.bisect_left(pts,t)
        if i==len(pts):return i-1
        if i and abs(pts[i-1]-t)<=abs(pts[i]-t):return i-1
        return i
    selected={};scenes=set()
    for t in timestamps(duration):selected.setdefault(nearest(t),[]).append(t)
    for t in scene_pts:
        i=nearest(t);selected.setdefault(i,[]);scenes.add(i)
    indices=sorted(selected)
    with tempfile.TemporaryDirectory(prefix='frames-') as tmp:
        expression='+'.join(f'eq(n,{n})' for n in indices)
        command([ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-i',str(video),'-an','-vf',f"select='{expression}',scale=720:-2",'-vsync','0','-q:v','2',str(Path(tmp)/'%06d.jpg')])
        images=sorted(Path(tmp).glob('*.jpg'))
        if len(images)!=len(indices):raise ValueError('Decoded frame count does not match timestamps')
        entries=[];segments=source_segments(record);base=record['detail_url'].rstrip('/')
        for i,img in zip(indices,images):
            t=pts[i];name=f'{round(t*100):06d}.jpg';dest=out/'frames'/name
            if dest.exists():raise ValueError('Timestamp filename collision')
            dest.write_bytes(img.read_bytes())
            with Image.open(dest) as im:width,height=im.size
            entries.append({'timestamp':t,'timestampLabel':label(t),'requestedSampleTimestamps':selected[i],'imageUrl':f'{base}/frames/{name}','transcriptSegment':segment_at(segments,t),'transcriptTiming':'source_segment' if segments else 'unavailable','sceneChange':i in scenes,'width':width,'height':height})
    text=record.get('transcript');text=text.get('text') if isinstance(text,dict) else text
    generated=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    creator=record.get('creator') or {};creator=(creator.get('name') or creator.get('username')) if isinstance(creator,dict) else creator
    manifest={'schemaVersion':'1.0','id':record['id'],'slug':record['id'],'creator':creator or None,'title':record.get('internal_title'),'sourceUrl':record.get('original_instagram_url'),'referencePageUrl':base,'videoUrl':record.get('video_url'),'reviewPdfUrl':base+'/review.pdf','analysisJsonUrl':base+'/analysis.json','aiTextUrl':base+'/ai.txt','durationSeconds':duration,'caption':record.get('caption'),'transcript':{'text':text,'segments':segments,'timing':'source_segment' if segments else 'unavailable'},'frames':entries,'sceneChanges':[{'timestamp':e['timestamp'],'imageUrl':e['imageUrl']} for e in entries if e['sceneChange']],'sampling':{'first5SecondsInterval':.25,'next10SecondsInterval':.5,'remainingInterval':1,'sceneThreshold':.30,'deduplication':'Same decoded source frame is included once; scheduled samples snap to the nearest real frame.','timestampBasis':'Decoded source frame presentation timestamp relative to first frame.'},'generatedAt':generated,'generatorVersion':VERSION,'sourceVideoSha256':hashlib.sha256(video.read_bytes()).hexdigest(),'limitations':['No timed transcript was stored; frame-to-speech binding is unavailable.'] if not segments else []}
    pdfmetrics.registerFont(TTFont('Evidence',str(font)))
    W,H=A3;margin=42;c=canvas.Canvas(str(out/'review.pdf'),pagesize=A3,pageCompression=1)
    c.setTitle((manifest['title'] or 'Reel')+' - Visual Review');c.setAuthor('Mohaned Reel Reference Lab')
    style=ParagraphStyle('body',fontName='Evidence',fontSize=11,leading=15,textColor='#111111',wordWrap='CJK')
    def paragraph(text,x,y,width,size=11):
        style.fontSize=size;style.leading=size*1.36
        p=Paragraph(escape(str(text)).replace('\n','<br/>'),style);_,h=p.wrap(width,H);p.drawOn(c,x,y-h);return y-h
    def footer(page):
        c.setFont('Evidence',9);c.drawString(margin,22,'Evidence only - no AI interpretation');c.drawRightString(W-margin,22,f'Page {page}')
    c.setFont('Evidence',21);c.drawString(margin,H-margin,'VISUAL REVIEW - REEL EVIDENCE')
    y=H-margin-38
    fields=[('Creator',creator),('Reference title',manifest['title']),('Reference ID',record['id']),('Reference slug',record['id']),('Original source URL',manifest['sourceUrl']),('Original video URL',manifest['videoUrl']),('Duration',f'{duration:.3f} seconds'),('Transcript available','Yes' if text else 'No'),('Number of extracted frames',len(entries)),('Generated date/time',generated),('Caption',manifest['caption'] or 'Not available')]
    for key,value in fields:y=paragraph(f'{key}: {value if value is not None else "Not available"}',margin,y,W-2*margin,11)-12
    if y<110:raise ValueError('Cover content does not fit; preserve content and use a larger cover layout.')
    y=paragraph('Timestamps below the frames are actual source frame times. Sampling requests are snapped to the nearest decoded frame.',margin,y,W-2*margin,10)-15
    if not segments:y=paragraph('Transcript timing is unavailable. No spoken text has been assigned to individual frames. The original transcript is included after the visual pages.',margin,y,W-2*margin,10)-15
    c.setFont('Evidence',16);c.drawString(margin,65,'VISUAL REVIEW STARTS ON PAGE 2');footer(1);c.showPage()
    page=2;gap=26;cellw=(W-2*margin-gap)/2;cellh=(H-2*margin-34)/2
    for offset in range(0,len(entries),4):
        c.setFont('Evidence',13);c.drawString(margin,H-27,'TIMESTAMPED VIDEO FRAMES')
        for pos,entry in enumerate(entries[offset:offset+4]):
            col=pos%2;row=pos//2;x=margin+col*(cellw+gap);top=H-margin-row*cellh
            area_h=cellh-(100 if segments else 58);scale=min(cellw/entry['width'],area_h/entry['height']);iw=entry['width']*scale;ih=entry['height']*scale
            imagefile=out/'frames'/entry['imageUrl'].rsplit('/',1)[-1]
            c.drawImage(ImageReader(str(imagefile)),x+(cellw-iw)/2,top-ih,iw,ih,preserveAspectRatio=True)
            y=top-ih-19;c.setFont('Evidence',12);c.drawString(x,y,entry['timestampLabel']+('  - scene change' if entry['sceneChange'] else ''))
            spoken=entry['transcriptSegment']
            if spoken:paragraph('Spoken (source segment): '+spoken,x,y-9,cellw,9)
            elif not segments:paragraph('Spoken: timing unavailable',x,y-9,cellw,9)
        footer(page);c.showPage();page+=1
    if text:
        c.setFont('Evidence',18);c.drawString(margin,H-margin,'STORED TRANSCRIPT');y=H-margin-38
        y=paragraph('Source: existing stored transcript. Timing is not inferred.',margin,y,W-2*margin,10)-20
        # Paginate paragraph chunks without modifying stored text.
        words=text.split();chunk=[]
        for word in words:
            trial=' '.join(chunk+[word]);p=Paragraph(escape(trial),ParagraphStyle('transcript',fontName='Evidence',fontSize=12,leading=18));_,h=p.wrap(W-2*margin,H)
            if h>y-65 and chunk:
                paragraph(' '.join(chunk),margin,y,W-2*margin,12);footer(page);c.showPage();page+=1;y=H-margin;chunk=[word]
            else:chunk.append(word)
        if chunk:paragraph(' '.join(chunk),margin,y,W-2*margin,12)
        footer(page);c.showPage()
    c.save()
    (out/'analysis.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    ai='MOHANED REEL REFERENCE LAB\n\n'+'\n\n'.join(f'{key}:\n{value if value is not None else "Not available"}' for key,value in [('REFERENCE',manifest['title']),('CREATOR',creator),('DURATION',str(duration)+' seconds'),('REFERENCE PAGE',base),('ORIGINAL VIDEO',manifest['videoUrl']),('VISUAL REVIEW PDF',manifest['reviewPdfUrl']),('ANALYSIS JSON',manifest['analysisJsonUrl']),('TRANSCRIPT',text),('TRANSCRIPT TIMING','Source segments available' if segments else 'Unavailable; do not infer frame-to-speech alignment'),('CAPTION',manifest['caption'])])+'\n'
    (out/'ai.txt').write_text(ai)
    print(json.dumps({'id':record['id'],'frames':len(entries),'sceneChanges':len(manifest['sceneChanges']),'duration':duration,'output':str(out)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--record',required=True,type=Path);parser.add_argument('--video',required=True,type=Path);parser.add_argument('--out',required=True,type=Path);parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe');parser.add_argument('--font',required=True,type=Path);a=parser.parse_args();build(json.loads(a.record.read_text()),a.video,a.out,a.ffmpeg,a.ffprobe,a.font)
