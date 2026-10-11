"""Small explicit fixes after inspecting the built mobile screenshots.
Works only on the expected feature tree; no deployment or user data access.
"""
from pathlib import Path

def replace(path, old, new):
    p=Path(path); text=p.read_text()
    assert text.count(old)==1, (path,text.count(old),old[:80])
    p.write_text(text.replace(old,new))

replace('frontend/src/vision-xray/visualStyle.ts', '`;', '''
/* Native WebKit select appearance otherwise paints a white bezel under light text. */
.vx-catalog-category{-webkit-appearance:none;appearance:none;color-scheme:dark;background-color:#122c3b;background-image:linear-gradient(45deg,transparent 50%,#b7d5e3 50%),linear-gradient(135deg,#b7d5e3 50%,transparent 50%);background-position:calc(100% - 18px) 19px,calc(100% - 13px) 19px;background-size:5px 5px,5px 5px;background-repeat:no-repeat;padding-right:32px;color:#e0f3f8}
`;''')
replace('frontend/src/vision-xray/LiveExplorer.web.tsx', "'Flash n/d'", "'Flash non disponibile'")
replace('frontend/e2e/vision-catalog-camera.spec.ts',
    "await page.getByTestId('vision-catalog-category').selectOption('Casa');await expect",
    "await page.getByTestId('vision-catalog-category').selectOption('Casa');await expect(page.getByTestId('vision-catalog-category')).toHaveCSS('appearance','none');await expect")
replace('frontend/e2e/vision-catalog-camera.spec.ts',
    "await page.screenshot({path:'../.vision-evidence/camera-flash-zoom-'+info.project.name+'.png',fullPage:true});",
    """await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-arrival','complete');
 await page.screenshot({path:'../.vision-evidence/camera-flash-zoom-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-camera-zoom-toggle').click();
 await page.screenshot({path:'../.vision-evidence/camera-zoom-panel-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-camera-zoom-toggle').click();""")
replace('.github/workflows/vision-catalog-live.yml',
    'backend/vision_catalog.py backend/vision_xray.py backend/vision_tests',
    'backend/vision_catalog.py backend/vision_seed_library.py backend/vision_xray.py backend/vision_tests')
