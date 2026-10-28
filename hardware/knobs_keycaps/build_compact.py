# v02 compact knobs (user: D20 knob looked fat on the 3mm test plate). Same SCOOP shape, shallow scoop (SC=7),
# rounded top rim, bore 6.1 (6.0 too tight / 6.2 loose on the SH16K4 knurl). Printed upright, no supports.
import cadquery as cq
from pathlib import Path
P=Path(__file__).resolve().parents[1]
SC=7.0
def knob(D,Hk,hole,depth,label):
    f=D/20.0
    k=cq.Workplane('XY').circle(D/2).extrude(Hk).val()
    prof=cq.Workplane('XY').moveTo(0,-11.5*f).ellipseArc(10.5*f,11.5*f,-90,90,startAtCurrent=True).close()
    ell=prof.revolve(360,(0,-1,0),(0,1,0)).val().translate((0,-6.5*f,Hk+SC*f))
    k=k.cut(ell)
    # v02b: one fillet over the whole top: outer rim + the scoop's edge (no sharp lip where the scoop meets the wall)
    sc=max([fc for fc in k.Faces() if fc.geomType()=='REVOLUTION'],key=lambda x:x.Area())
    top=[fc for fc in k.Faces() if fc.geomType()=='PLANE' and fc.Center().z>Hk-0.01][0]
    k=k.fillet(round(0.05*D,2),   # v02c: 0.09D looked too soft -> 0.05D
        list({e.hashCode():e for e in sc.Edges()+top.Edges()}.values()))
    k=cq.Workplane('XY').add(k)
    k=k.faces('<Z').edges().chamfer(0.35)
    k=k.faces('<Z').workplane().hole(hole,depth)
    k=k.cut(cq.Workplane('XY').box(0.6,D/2-1.2,depth,centered=(True,False,False)))
    k=k.cut(cq.Workplane('XY').text(label,1.6 if D<16 else 2.0,0.4,kind='bold',halign='center').mirror('YZ').translate((0,-D/2+2.3,0)))
    floor=Hk-(10.5-SC)*f;assert floor>depth+0.8,(label,floor,depth)
    return k.val()
if __name__=='__main__':
  V=[('C14',14,12,8.5),('C16',16,13,9),('C17',17,14,9)]
  asm=None
  for i,(n,D,H,dep) in enumerate(V):
    s=knob(D,H,6.1,dep,n).translate((i*21,0,0));assert s.isValid(),n
    s.exportStl(str(P/'stl'/f'knob_compact_{n}.stl'),tolerance=.01,angularTolerance=.05)
    asm=s if asm is None else asm.fuse(s)
  asm.exportStl(str(P/'stl'/'ALL_compact_knobs.stl'),tolerance=.01,angularTolerance=.05)
  print('ok')
