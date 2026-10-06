"""Generate original sample art and reproducible light/dark UI screenshots."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/contact-sheet-preview-cache")
import math
import tempfile
import time
from pathlib import Path
from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from contact_sheet.gui import MainWindow
from contact_sheet.themes import apply_theme
from contact_sheet.core import export_sheets

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'

def sample_art(path,index):
    palette=[('#d8c7ae','#516768','#829c9b'),('#b8c5c6','#415761','#829988'),('#cabbb2','#5e6b70','#ae8c69'),('#d3c9bb','#7e8e9a','#b39572')]
    bg,mountain,front=palette[index%4]
    w,h=(1000,680) if index%3 else (720,980)
    im=Image.new('RGB',(w,h),bg); d=ImageDraw.Draw(im)
    d.ellipse((w*.62,h*.12,w*.79,h*.12+w*.17),fill='#f2e5c9')
    d.polygon([(0,h*.68),(w*.26,h*.27),(w*.57,h*.69),(w*.81,h*.40),(w,h*.61),(w,h),(0,h)],fill=mountain)
    d.polygon([(0,h*.81),(w*.29,h*.57),(w*.51,h*.83),(w*.76,h*.63),(w,h*.80),(w,h),(0,h)],fill=front)
    for i in range(5):
        y=h*(.88+i*.023); d.line((0,y,w,y-18),fill=bg,width=3)
    im.save(path)

def main():
    app=QApplication([]); app.setStyle('Fusion')
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp)
        paths=[]
        for i in range(14):
            p=temp/f'Study_{i+1:02d}.jpg'; sample_art(p,i); paths.append(p)
        settings=QSettings(str(temp/'settings.ini'),QSettings.IniFormat)
        w=MainWindow(settings); w.show(); w.title_input.setText('Landscape studies'); w._apply_preset(0)
        w.add_paths(paths)
        until=time.monotonic()+30
        while w.busy or w.preview_task or w.preview_pending:
            app.processEvents(); time.sleep(.01)
            if time.monotonic()>until: raise RuntimeError('Preview timed out')
        OUT.mkdir(exist_ok=True)
        for theme in ['dark','light']:
            apply_theme(app,theme); app.processEvents(); w.grab().save(str(OUT/f'screenshot-{theme}.png'))
        w.resize(890,700); app.processEvents(); w.grab().save(str(OUT/'screenshot-compact.png'))
        outputs=OUT/'sample-export'; outputs.mkdir(exist_ok=True)
        export_sheets(w.model.photos,w.sheet_settings(),outputs,stem='landscape-studies',format='PDF',overwrite=True)
        export_sheets(w.model.photos,w.sheet_settings(),outputs,stem='landscape-studies',format='JPEG',overwrite=True)
        w.close()
    print('Screenshots and sample PDF/JPEG export written to',OUT)

if __name__=='__main__':main()
