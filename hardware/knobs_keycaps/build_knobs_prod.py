# Production small knobs (fit test 10/27): C14 chosen (C16 tried, C14 looks better in a row), round bore 6.05 fits the SH16K4 knurl. 6 pcs, 0.2 nozzle.
import sys;from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from build_compact import knob,P
asm=None
for i in range(6):
    s=knob(14,12,6.05,8.5,'6.05').translate(((i%3)*18,(i//3)*18,0));assert s.isValid()
    asm=s if asm is None else asm.fuse(s)
(P/'stl'/'plate_0.2').mkdir(exist_ok=True)
asm.exportStl(str(P/'stl'/'plate_0.2'/'knobs_C14_x6_bore6.05.stl'),tolerance=.01,angularTolerance=.05)
b=asm.BoundingBox();print('ok',round(b.xlen,1),round(b.ylen,1),round(b.zlen,1))
