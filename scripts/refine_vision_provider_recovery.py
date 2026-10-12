from pathlib import Path

def replace(path, old, new):
 p=Path(path);s=p.read_text();assert s.count(old)==1,(path,old[:80]);p.write_text(s.replace(old,new))
replace('backend/vision_provider.py',
 '''    parts=candidate.get("content",{}).get("parts",[])
    text="".join''',
 '''    content=candidate.get("content")
    if not isinstance(content,dict) or not isinstance(content.get("parts"),list):
        raise VisionProviderError("invalid_model_response")
    parts=content["parts"]
    text="".join''')
replace('frontend/src/vision-xray/LiveExplorer.web.tsx',
 "  const [needsHint,setNeedsHint]=useState(false);",
 "  const [needsHint,setNeedsHint]=useState(false);\n  const needsHintRef=useRef(false);needsHintRef.current=needsHint;")
replace('frontend/src/vision-xray/LiveExplorer.web.tsx',
 "if(live&&!scene.current&&v?.videoWidth&&pixels&&time-lastSample>120)",
 "if(live&&!scene.current&&!needsHintRef.current&&v?.videoWidth&&pixels&&time-lastSample>120)")
p=Path('backend/vision_tests/test_provider_recovery.py')
p.write_text(p.read_text()+'''
@pytest.mark.parametrize('content',[None,[],42,{'parts':None},{'parts':'invalid'}])
def test_bad_content_envelope_returns_structured_error(content):
    with pytest.raises(provider.VisionProviderError):
        provider.parse_response({'candidates':[{'content':content}]})
''')
p=Path('frontend/e2e/vision-provider-recovery.spec.ts')
p.write_text(p.read_text()+'''

test('automatic retries pause while the user supplies an object hint',async({page,browserName})=>{
 test.skip(browserName==='webkit','Synthetic canvas video is not a physical WebKit camera test.');
 let scans=0;
 await page.addInitScript(()=>{
  const devices={getUserMedia:async()=>{
   const canvas=document.createElement('canvas');canvas.width=320;canvas.height=480;const ctx=canvas.getContext('2d')!;let n=0;
   const draw=()=>{ctx.fillStyle=++n%2?'#aabbcc':'#334455';ctx.fillRect(0,0,320,480);ctx.fillStyle='#222';ctx.fillRect(90,90,140,250);};
   draw();setInterval(draw,120);return canvas.captureStream(24);
  }};Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>devices});
 });
 await page.route('**/api/vision-xray/scan',route=>{scans++;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'unknown',code:'recognition_uncertain',can_describe:true,reason:'Puoi indicarmi che oggetto è.'})});});
 await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
 await expect(page.getByTestId('vision-recovery')).toBeVisible();
 await page.getByTestId('vision-object-hint').fill('un telecomando');
 await page.waitForTimeout(7000);
 expect(scans).toBe(1);await expect(page.getByTestId('vision-object-hint')).toHaveValue('un telecomando');
 await page.getByTestId('vision-identify-hint').click();await expect.poll(()=>scans).toBe(2);
 await page.getByTestId('vision-stop-camera').click();await expect(page.getByTestId('vision-recovery')).toHaveCount(0);
});
''')
