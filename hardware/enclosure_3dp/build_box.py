# 3D-printed tray enclosures for the two small boxes (layout_v07_geisai.json). The 1.2mm top plate sits on the
# wall tops and is screwed down with M3 x15 into the corner bosses (2.6 pilot = self-tapping into PLA).
# cadStack: caseHeight 25.5 incl. top plate, wall 2, floor 2. Printed open side up, no supports.
import cadquery as cq, json
from pathlib import Path
P=Path(__file__).resolve().parents[1]
LAY=json.load(open(P.parent/'layout_v07_geisai.json'))
WALL,FLOOR,TOPPLATE,CASEH=2.0,2.0,1.2,25.5
BOSS_D,PILOT,PILOT_DEPTH=7.4,2.85,15.0   # v01d: 2.6 was too tight for M3 in PLA (screw would not turn)
def box(board,caseh=CASEH):
    L=board['layout'];W,H,R=L['panel']['width'],L['panel']['height'],L['panel']['cornerRadius']
    h=caseh-TOPPLATE
    holes=[(i['x']-W/2,H/2-i['y']) for i in L['instances'] if i.get('partId')=='m3_screw']
    b=cq.Workplane('XY').rect(W,H).extrude(h).edges('|Z').fillet(R)
    b=b.faces('<Z').edges().chamfer(0.6)
    inner=cq.Workplane('XY').rect(W-2*WALL,H-2*WALL).extrude(h).edges('|Z').fillet(max(R-WALL,0.5)).translate((0,0,FLOOR))
    b=b.cut(inner)
    for x,y in holes:   # corner bosses, merged into the walls, small fillet at the floor
        b=b.union(cq.Workplane('XY').circle(BOSS_D/2).extrude(h-FLOOR).translate((x,y,FLOOR)))
        b=b.cut(cq.Workplane('XY').circle(PILOT/2).extrude(PILOT_DEPTH).translate((x,y,h-PILOT_DEPTH)))
    return b.val(),(W,H,h,len(holes))
for bd,name in [(LAY['boards'][2],'box_keys_115x80'),(LAY['boards'][1],'box_faders_110x105')]:
    s,info=box(bd);assert s.isValid()
    s.exportStl(str(P/'stl'/f'{name}.stl'),tolerance=.02,angularTolerance=.1)
    print(name,info)
# v01c (10/27): main box 120x140 exactly as the layout tool's CAD (casePortOpenings / internalFloorHoles in layout_2d.html):
# height = the other two boxes (25.5), Pi Zero (RP2350 Pi Zero) on 5mm standoffs at x42.5/y17.5 rot 0,
# its 3 connectors (mini HDMI, PIO USB-C, USB-C) through the back wall (layout y=0) with 0.5 clearance and R0.8,
# plus the 4 standoff holes (2.7) in the floor.
import re
LAY8=json.load(open(P.parent/'layout_v08c_browser_20261026.json'));B=LAY8['boards'][0]['layout']
HT=open(Path.home()/'Documents/Codex/2026-10-07/new-chat/outputs/layout_2d.html',encoding='utf8',errors='replace').read()
k=HT.find('"rp2350_pizero":{"source"')+len('"rp2350_pizero":');PI=json.JSONDecoder().raw_decode(HT[k:])[0]
s,info=box(LAY8['boards'][0]);W,H,h,_=info   # user: same height as the other two (tool's 16 is too low: toggle/knobs need ~20 under the plate)
pz=[i for i in B['instances'] if i.get('partId')=='rp2350_pizero'][0];assert pz.get('rotation',0)==0
CL,RAD=0.5,0.8;z0=FLOOR+pz.get('mountHeight',5)
s=cq.Workplane('XY').add(s)
# v01f (10/27, test fit photo): the real RP2350-PiZero, components up with its ports to the back wall, has USB on the
# left and mini HDMI on the right -> the tool's model is mirrored in X. Mirror the port x about the board centre.
for pt in PI['ports']:
    px=pz['x']-pt['x']
    w,hh=pt['width']+2*CL,pt['height']+2*CL;zc=z0+pt['z']-CL+hh/2
    # v01g: the middle hole is widened 3mm to the left so it also passes the Raspberry Pi Zero v1.3's micro-USB OTG
    # (same 65x30 board and holes; its PWR micro-USB sits at the USB-C hole and its mini HDMI at the HDMI hole)
    if pt['name']=='PIO USB-C':w+=3;px-=1.5   # 28.75..41.75, keeps a 2mm web to the USB-C hole
    s=s.cut(cq.Workplane('XZ').rect(w,hh).extrude(-WALL*3).edges('|Y').fillet(RAD).translate((px-W/2,H/2-WALL*1.5,zc)))
    print(' port',pt['name'],'x',round(px,2),'z',round(zc-hh/2,2),'..',round(zc+hh/2,2))
# v01e: printed 5mm standoffs instead of floor through-holes (no spacers, flat bottom). M2 self-tap pilot 1.7 (same black M2x5 as the cup phone lid; Pi holes 2.75 pass M2).
for fh in PI['floorHoles']:
    cx,cy=pz['x']+fh['x']-W/2,H/2-(pz['y']+fh['y']);mh=pz.get('mountHeight',5)
    s=s.union(cq.Workplane('XY').circle(2.75).extrude(mh+0.5).translate((cx,cy,FLOOR-0.5)))
    s=s.cut(cq.Workplane('XY').circle(0.85).extrude(mh).translate((cx,cy,FLOOR)))
s=s.val();assert s.isValid();s.exportStl(str(P/'stl'/'box_main_120x140.stl'),tolerance=.02,angularTolerance=.1)
print('box_main_120x140',info)
