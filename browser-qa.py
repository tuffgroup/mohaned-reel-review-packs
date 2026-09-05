"""Public browser QA in a fresh, unauthenticated Chromium context."""
import asyncio
from playwright.async_api import async_playwright
SITE='https://mohaned-reel-reference-lab.blsi.chatgpt.site'
IDS=['6a07a4f0-38eb-4987-a6e4-68d1c9af865b','1a8a20da-2e59-4fff-a3a3-45e0d4fadca0']
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path="/usr/bin/google-chrome")
  context=await browser.new_context()
  assert await context.cookies()==[]
  page=await context.new_page()
  for path in ['/', '/references','/references/unreviewed','/api/references/latest','/api/references?status=needs_review&limit=10']:
   print("Checking",path,flush=True)
   response=await page.goto(SITE+path)
   assert response.status==200,(path,response.status)
   assert page.url.startswith(SITE+path.split('?')[0]),page.url
  for rid in IDS:
   print("Checking Reel",rid,flush=True)
   response=await page.goto(SITE+'/references/'+rid)
   assert response.status==200
   assert 'noindex' in await page.locator('meta[name="robots"]').get_attribute('content')
   await asyncio.wait_for(page.locator('video').evaluate('(v)=>{v.muted=true;return v.play()}'),30)
   await page.wait_for_function('document.querySelector("video").currentTime > 0.3')
   assert await page.locator('video').evaluate('(v)=>v.videoWidth>0 && !v.error')
   await page.locator('video').evaluate('(v)=>v.pause()')
   for name in ['Visual Review','Analysis JSON','AI Text']:
    link=page.get_by_role('link',name=name,exact=True)
    href=await link.get_attribute('href')
    assert href
    asset=await context.request.get(href if href.startswith('http') else SITE+href)
    assert asset.status==200,(name,asset.status)
    assert len(await asset.body())>100
   print('PASS fresh anonymous browser: page, original video playback and three Review Pack links',rid,flush=True)
  for path in ['/settings','/admin']:
   response=await context.request.get(SITE+path,max_redirects=0)
   assert response.status in [302,303,307,308,401,403,404],(path,response.status)
  assert all('session' not in c['name'].lower() for c in await context.cookies())
  await browser.close()
 print('PASS fresh browser public root/library/JSON; private settings/admin denied',flush=True)
asyncio.run(asyncio.wait_for(main(),180))
