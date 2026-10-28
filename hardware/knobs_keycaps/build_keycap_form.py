# v03 keycap, FormKey / MX Keys style (user picked it 10/27): low tapered square, wide shallow spherical dish
# almost edge to edge, soft top rim. Cross 4.25x1.40 (fit test v01). Printed upright, no supports, 0.2 nozzle.
import cadquery as cq
from pathlib import Path
P=Path(__file__).resolve().parents[1]
W,Dp,Hc,T=17.0,16.0,6.5,2.2      # same footprint/height as v01 keycap (fits the 18/17 grid)
TP=1.0                           # top is 1.0 smaller than the base (side taper ~4.4deg)
RC=2.2                           # corner radius at the base
RD,SAG=6.6,0.8                   # dish: radius 6.6 on the top face, 0.8 deep at the centre
def keycap(cw=4.25,ct=1.40,label='4.25'):
    s0=cq.Sketch().rect(W,Dp).vertices().fillet(RC)
    s1=cq.Sketch().rect(W-TP,Dp-TP).vertices().fillet(RC-TP/2).moved(cq.Location(cq.Vector(0,0,Hc)))
    c=cq.Workplane('XY').placeSketch(s0,s1).loft()
    c=c.faces('>Z').edges().fillet(0.6)
    R=(RD**2+SAG**2)/(2*SAG)
    c=c.cut(cq.Workplane('XY').sphere(R).rotate((0,0,0),(1,0,0),90).translate((0,0,Hc-SAG+R)))
    c=c.cut(cq.Workplane('XY').rect(W-3.0,Dp-3.0).extrude(Hc-T))
    c=c.union(cq.Workplane('XY').circle(2.8).extrude(Hc-T))
    c=c.cut(cq.Workplane('XY').rect(cw,ct).extrude(Hc-T-0.4).union(cq.Workplane('XY').rect(ct,cw).extrude(Hc-T-0.4)))
    c=c.cut(cq.Workplane('XY').text(label,1.8,0.4,kind='bold',halign='center').mirror('YZ').translate((0,-5.0,Hc-T-0.4)))
    return c.val()
if __name__=='__main__':
    k=keycap();assert k.isValid()
    k.exportStl(str(P/'stl'/'keycap_form_v03.stl'),tolerance=.01,angularTolerance=.05)
    asm=k.fuse(keycap().translate((21,0,0)))
    asm.exportStl(str(P/'stl'/'plate_0.2'/'keycap_form_v03_x2.stl'),tolerance=.01,angularTolerance=.05)
    print('ok')
    # production (10/27, user: "あれでいきたい"): 8 keys on the panel, 2 already printed -> 6 more
    if 'prod' in __import__('sys').argv:
        asm=None
        for i in range(6):
            s=keycap().translate(((i%3)*21,(i//3)*20,0))
            asm=s if asm is None else asm.fuse(s)
        asm.exportStl(str(P/'stl'/'plate_0.2'/'keycap_form_v03_x6.stl'),tolerance=.01,angularTolerance=.05)
        print('x6 ok')
