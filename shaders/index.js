// Shader list for the emulator (file:// pages cannot list or fetch files, so the sources live here).
// Each entry is a GLSL ES 1.00 fragment shader body: write main(); the host adds precision + uniforms
// (see AGENTS.md "Shader contract"). Keep the same text runnable on the Pi Zero.
//
// u_good (GOOD KNOB) grows without limit: 1.0 per full turn of the encoder, 0 after RESET.
// Never use it raw where it can blow up. Use it through bounded shapes: g01() saturates, fract()/sin() cycle,
// log() keeps adding detail slower and slower, so turning "always makes it a bit better" and never breaks.
window.SHADERS = [

{ name: 'TRUCHET', src: `
// メインの模様（つまみの割り当てはあとで）。背景 #fffaf0 に正方形のマスを敷き詰め、各マスに 1/4 円の弧を2本描く。
// 弧1は右の辺と上の辺を、弧2は下の辺と左の辺をつなぐので、隣のマスの弧とつながって線になる。線は #7fffd4 と #00bfff。
// ・各マスに、2本ずつ平行な線の束を2組入れる（手描きのスケッチ 2026-10-28 から）。
//   曲がる束：右上の角を中心にした2重の 1/4 円（#00bfff）。上を通る。
//   まっすぐな束：縦2本と横2本（#7fffd4）。曲がる束とぶつかる所で途切れて、下をくぐる。
//   マスごとに向き（90 度ずつ4通り）が違うので、束が曲がったりくぐったりしながらつながっていく。
// ・画面全体がずっと左上から右下へ流れる。
// ・ときどきランダムに1マスがカードのようにこちらへ浮き上がり、縦軸か横軸のまわりでクルンと半回転して着地する。
//   裏の面には、別の向き（90 度ずつ回した4通りのどれか）の同じ模様があるので、着地するとそのマスの向きが変わる。
//   最初は全部同じ向きでそろっているが、時間とともに向きのばらけたトルシェタイルに近づいていく。
// ・同時に回るマスは、画面全体で平均2〜3個（多くても6個くらい）になるように頻度を決めている。
uniform float p_scroll; // @param 0.0 1.0 0.2 流れる速さ（1秒に進むマス数）
uniform float p_every;  // @param 5.0 120.0 30.0 1マスが回る平均の間隔（秒）。小さいほど、ばらけるのが早い
uniform float p_flip;   // @param 0.6 3.0 1.4 1回の半回転にかける時間（秒）
uniform float p_roll;   // @param 0.0 2.0 0.5 玉の速さ（1秒に進む弧の数）
uniform float p_rule;   // @param 0.0 5.99 0.0 もとの並びの規則: 0 全部同じ 1 市松 2 行ごと 3 2x2市松 4 同心円 5 ゆっくり動く場

float hash(vec2 v){return fract(sin(dot(v,vec2(127.1,311.7)))*43758.5453);}
float smoother(float f){return f*f*f*(f*(f*6.0-15.0)+10.0);}
// もとの並びで左右反転するかどうか（規則ごと）
float flipOf(vec2 cell,float cells){
  float r=floor(p_rule);
  if(r<0.5) return 0.0;
  if(r<1.5) return mod(cell.x+cell.y,2.0);
  if(r<2.5) return mod(cell.y,2.0);
  if(r<3.5) return mod(floor(cell.x*0.5)+floor(cell.y*0.5),2.0);
  if(r<4.5){vec2 c=(cell+0.5)-vec2(0.5*cells*u_resolution.x/u_resolution.y,0.5*cells);return mod(floor(length(c)),2.0);}
  return step(0.0,sin(cell.x*0.45+u_time*0.3)+sin(cell.y*0.38-u_time*0.23)+sin((cell.x+cell.y)*0.21));
}
// マスの予定表：回る間隔とずれはマスごとにランダム。n 回目の半回転を終えると向きが orient(n) になる。
// 戻り値 x = 今の半回転の進み 0..1（回っていなければ 1）、y = 回る前の向き、z = 回ったあとの向き、w = 回転軸（0 縦、1 横）
vec4 schedule(vec2 cell){
  // いまは浮き上がって回る動きをお休み中：各マスはランダムな向きで止まったまま（p_every などは使っていない）
  float o0=floor(hash(cell+9.9)*4.0);
  if(true) return vec4(1.0,o0,o0,0.0);
  float I=p_every*(0.6+0.8*hash(cell+1.3));
  float first=2.0+hash(cell+7.1)*p_every*1.5;        // 最初の半回転の時刻（ここまでは全部そろった向き）
  float tt=u_time-first;
  if(tt<0.0) return vec4(1.0,0.0,0.0,0.0);
  float n=floor(tt/I),f=(tt-n*I)/p_flip;
  float newO=floor(hash(cell+vec2(n*1.7+0.3,n*3.1))*4.0);
  float oldO=n<0.5?0.0:floor(hash(cell+vec2((n-1.0)*1.7+0.3,(n-1.0)*3.1))*4.0);
  float axis=step(0.5,hash(cell+vec2(n*5.3,n*2.9)));
  return vec4(min(f,1.0),f<1.0?oldO:newO,newO,axis);
}
// 中心 c・半径 0.5 の弧（角度 t0 から 90 度ぶん、両端が丸い）までの距離
float arcSeg(vec2 q,vec2 c,float t0){
  vec2 v=q-c;float t=t0+mod(atan(v.y,v.x)-t0,6.2831853);
  if(t<=t0+1.5707963) return abs(length(v)-0.5);
  vec2 e0=c+0.5*vec2(cos(t0),sin(t0)),e1=c+0.5*vec2(cos(t0+1.5707963),sin(t0+1.5707963));
  return min(length(q-e0),length(q-e1));
}
// タイルの中の線：dOver = 曲がる束（上）までの距離、dUnder = まっすぐな束（下）までの距離
void tileLines(vec2 q,out float dOver,out float dUnder){
  float r=length(q-vec2(1.0));
  dOver=min(abs(r-0.3333),abs(r-0.6667));
  dUnder=min(min(abs(q.x-0.3333),abs(q.x-0.6667)),min(abs(q.y-0.3333),abs(q.y-0.6667)));
  if(q.x<0.0||q.y<0.0||q.x>1.0||q.y>1.0){dOver=9.0;dUnder=9.0;}   // タイルの外には描かない
}
// マスの中の位置 uv（0..1）を、反転と向き o（90 度単位）を戻した「もとのタイル」の座標にする
vec2 tileQ(vec2 uv,float flip,float o){
  if(flip>0.5) uv.x=1.0-uv.x;
  float a=o*1.5707963;
  return mat2(cos(a),-sin(a),sin(a),cos(a))*(uv-0.5)+0.5;
}
void main(){
  float cells=5.0;                                   // 画面の縦に並ぶマスの数
  float px=cells/u_resolution.y;                     // 1ピクセルの大きさ（マス単位）
  vec2 p=gl_FragCoord.xy*px+u_time*p_scroll*vec2(-1.0,1.0);   // 左上から右下へ流れる
  float w=0.045,rb=0.032;                            // 線の半分の太さ、玉の半径（玉は線より細く）
  float s=fract(u_time*p_roll);
  vec3 colA=vec3(0.498,1.0,0.831),colB=vec3(0.0,0.749,1.0),bg=vec3(1.0,0.980,0.941),ballC=vec3(0.973,0.973,1.0);
  vec3 shadowC=vec3(0.78);                           // 影の色（薄いグレー）
  float off=2.5*px*0.7071;                           // 影は画面の右下 45 度に 2.5 ピクセル
  // ---- 地面の模様：止まっているマス（このマスと隣4マス） ----
  vec2 base=floor(p);
  float ld=9.0,lid=9.0,bd=9.0,sd=9.0,hole=0.0;
  for(int n=0;n<5;n++){
    vec2 o=n==1?vec2(1.0,0.0):n==2?vec2(-1.0,0.0):n==3?vec2(0.0,1.0):n==4?vec2(0.0,-1.0):vec2(0.0);
    vec2 cell=base+o;
    vec4 sc=schedule(cell);
    if(sc.x<1.0){if(n==0) hole=1.0;continue;}       // 浮き上がっているマスは地面に描かない
    float fl=flipOf(cell,cells),id=cell.x+cell.y;
    vec2 q=tileQ(p-cell,fl,sc.y),qs=tileQ(p+vec2(-off,off)-cell,fl,sc.y);
    float dO,dU;tileLines(q,dO,dU);
    ld=min(ld,dO);lid=min(lid,dU);                   // ld = 曲がる束（上）、lid = まっすぐな束（下）
    float t1=3.1415927+s*1.5707963;                  // 玉：曲がる束の2本の上を、上の辺から右の辺へ転がる
    vec2 B1=vec2(1.0)+0.3333*vec2(cos(t1),sin(t1)),B2=vec2(1.0)+0.6667*vec2(cos(t1),sin(t1));
    bd=min(bd,min(length(q-B1),length(q-B2)));
    sd=min(sd,min(length(qs-B1),length(qs-B2)));
  }
  vec3 c=bg;
  if(hole>0.5) c=mix(bg,vec3(0.86,0.84,0.80),0.6);  // カードが抜けた跡は少し暗く
  else{
    c=mix(c,colA,1.0-smoothstep(w-px,w+px,lid));              // まっすぐな束（下）
    c=mix(c,bg,1.0-smoothstep(w+2.0*px,w+3.0*px,ld));         // 曲がる束のまわりにすき間（下の線が途切れて、くぐって見える）
    c=mix(c,colB,1.0-smoothstep(w-px,w+px,ld));               // 曲がる束（上）
    if(sd<rb) c=shadowC;
    if(bd<rb) c=ballC;
  }
  // ---- 浮き上がって回るカード（周り9マスから探して、一番手前のものを描く） ----
  float bestS=0.0;
  for(int n=0;n<9;n++){
    vec2 cell=base+vec2(float(n-n/3*3)-1.0,float(n/3)-1.0);
    vec4 sc=schedule(cell);
    if(sc.x>=1.0) continue;
    float e=smoother(sc.x),th=3.1415927*e;          // 半回転の角度
    float S=1.0+0.35*sin(3.1415927*e);              // 浮き上がる分だけ大きく見せる
    vec2 rel=p-(cell+0.5);
    // カードの影（浮いた高さに合わせて右下へ）
    vec2 rs=rel-vec2(1.0,-1.0)*0.18*sin(3.1415927*e);
    float cs=cos(th);
    vec2 ls=sc.w<0.5?vec2(rs.x/(S*max(abs(cs),0.02)),rs.y/S):vec2(rs.x/S,rs.y/(S*max(abs(cs),0.02)));
    if(S>bestS&&max(abs(ls.x),abs(ls.y))<0.5) c=mix(c,shadowC,0.0)+(shadowC-c)*0.6;
    // カードの面：縦軸なら横幅が、横軸なら縦幅が cos で縮む
    vec2 l=sc.w<0.5?vec2(rel.x/(S*abs(cs)),rel.y/S):vec2(rel.x/S,rel.y/(S*abs(cs)));   // 裏面も鏡写しにせず、着地した向きのまま見せる
    if(abs(cs)<0.02||max(abs(l.x),abs(l.y))>0.5||S<=bestS) continue;
    bestS=S;
    float face=cs>0.0?sc.y:sc.z;                    // 表は回る前の向き、裏は新しい向き
    vec2 uv=l+0.5;
    float fl=flipOf(cell,cells),id=cell.x+cell.y;
    vec2 q=tileQ(uv,fl,face);
    float dO,dU;tileLines(q,dO,dU);
    vec3 cc=mix(bg,colA,1.0-smoothstep(w-px,w+px,dU));
    cc=mix(cc,bg,1.0-smoothstep(w+2.0*px,w+3.0*px,dO));
    cc=mix(cc,colB,1.0-smoothstep(w-px,w+px,dO));
    cc*=0.85+0.15*abs(cs);                           // 傾いている間は少し陰る
    c=cc;
  }
  gl_FragColor=vec4(c,1.0);
}`},

{ name: 'GOOD', map: {"p_zoom":{"src":"fader:0","inv":false},"p_spin":{"src":"fader:1","inv":false},"p_glow":{"src":"fader:2","inv":false}}, src: `
// GOOD KNOB: more mirrors, more colours, more shine, forever. params (map tab): zoom / spin / glow; key 0: flash; key 1: freeze rings
uniform float p_zoom; // @param 1.0 4.0 2.5 zoom
uniform float p_spin; // @param -0.5 0.5 0.0 spin speed
uniform float p_glow; // @param 0.0 1.0 0.5 centre glow
float g01(float g){return 1.0-exp(-max(g,0.0)*0.35);}
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*u_resolution)/u_resolution.y;
  float g=max(u_good,0.0),lg=log(1.0+g);
  float seg=3.0+floor(lg*3.0);                         // mirror count grows: 3,4,5,... slower and slower
  float a=atan(uv.y,uv.x)+u_time*p_spin;
  float r=length(uv)*p_zoom;
  float s=6.2831853/seg;a=abs(mod(a,s)-0.5*s);
  vec2 p=vec2(cos(a),sin(a))*r;
  float t=u_time*(1.0-u_key[1]);
  float v=sin(p.x*(8.0+lg*6.0)-t*2.0)+sin(p.y*(6.0+lg*5.0)+t*1.3)+sin(r*10.0-t*3.0);
  vec3 c=0.5+0.5*cos(v+g*0.15+vec3(0.0,2.1,4.2));     // hue walks with every detent
  c=mix(vec3(dot(c,vec3(0.333))),c,0.25+0.75*g01(g)); // starts almost grey, gets richer
  c+=pow(max(0.0,1.0-r),3.0)*p_glow*g01(g);            // centre glow, earned
  c+=u_key[0];
  gl_FragColor=vec4(c,1.0);
}`},

{ name: 'TUNNEL', map: {"p_speed":{"src":"fader:0","inv":false},"p_twist":{"src":"fader:1","inv":false},"p_rings":{"src":"knob:0","inv":false}}, src: `
// first shader written for the Pi Zero (cheap: no loops). params: speed / twist / rings; GOOD: more stripes and colour, a glow that grows; key 0: flash
uniform float p_speed; // @param 0.1 2.0 0.6 speed
uniform float p_twist; // @param -2.0 2.0 0.4 twist
uniform float p_rings; // @param 4.0 24.0 10.0 rings
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*u_resolution)/u_resolution.y;
  float g=max(u_good,0.0),lg=log(1.0+g);
  float r=length(uv)+1e-3,a=atan(uv.y,uv.x);
  float z=0.35/r+u_time*p_speed;                    // depth into the tunnel
  float stripes=floor(2.0+lg*3.0);                  // GOOD adds stripes, slower and slower
  float v=sin(z*p_rings)*0.5+0.5;
  float w=sin(a*stripes+z*p_twist*4.0)*0.5+0.5;
  vec3 c=0.5+0.5*cos(6.2831*(v*0.6+w*0.4)+g*0.12+vec3(0.0,2.1,4.2));
  c=mix(vec3(v*w),c,clamp(lg*0.8,0.15,1.0));        // starts monochrome, gets colour
  c*=smoothstep(0.0,0.25,r);                        // dark centre
  c+=exp(-r*8.0)*min(lg,2.0)*0.6;                    // glow that grows with GOOD
  c+=u_key[0]*0.6+u_beat*0.0;
  gl_FragColor=vec4(c,1.0);
}`},

{ name: 'BARS', src: `
// faders 0-2: bar count / roll speed / glitch; key 0: invert; key 1: tear; key 3: snow; GOOD: more bars, cleaner colours
float h(float n){return fract(sin(n)*43758.5453);}
void main(){
  vec2 uv=gl_FragCoord.xy/u_resolution;
  float g=max(u_good,0.0);
  float roll=u_time*(u_fader[1]*2.0-1.0)*0.5;
  uv.y=fract(uv.y+roll);
  float line=floor(uv.y*u_resolution.y);
  uv.x+=u_key[1]*0.2*(h(line+floor(u_time*30.0))-0.5);
  uv.x+=u_fader[2]*0.05*sin(uv.y*40.0+u_time*7.0)/(1.0+g*0.3);
  float n=floor(fract(uv.x)*(3.0+floor(u_fader[0]*13.0)+floor(log(1.0+g)*4.0)));
  vec3 c=vec3(mod(n,2.0),mod(floor(n/2.0),2.0),mod(floor(n/4.0),2.0));
  c=mix(c,1.0-c,u_key[0]);
  c=mix(c,vec3(h(dot(gl_FragCoord.xy,vec2(12.9,78.2))+u_time)),u_key[3]);
  gl_FragColor=vec4(c,1.0);
}`},

{ name: 'FEEDBACK', src: `
// fader 0: zoom; fader 1: rotate; fader 2: hue drift; fader 3: decay; key 0: new seed; beat: pulse; GOOD: longer trails
void main(){
  vec2 uv=gl_FragCoord.xy/u_resolution;
  float g=max(u_good,0.0);
  vec2 p=uv-0.5;
  float a=(u_fader[1]-0.5)*0.1;
  p=mat2(cos(a),-sin(a),sin(a),cos(a))*p*(1.0-(u_fader[0]-0.3)*0.06);
  vec3 prev=texture2D(u_prev,p+0.5).rgb;
  prev=prev.gbr*u_fader[2]+prev*(1.0-u_fader[2]);
  prev*=0.90+0.1*u_fader[3]-0.02/(1.0+g);
  float r=length(uv-0.5);
  float ring=smoothstep(0.02,0.0,abs(r-0.1-0.25*u_beat));
  vec3 seed=vec3(0.5+0.5*sin(u_time+g*0.3+vec3(0.0,2.0,4.0)))*ring;
  seed+=u_key[0]*step(r,0.05);
  gl_FragColor=vec4(max(prev,seed),1.0);
}`},

{ name: 'PLASMA', src: `
// knob 0/1: scale; faders: speed / contrast / posterize; key 2: mirror; key 4: scanlines; GOOD: smoother steps, more layers
void main(){
  vec2 uv=gl_FragCoord.xy/u_resolution*2.0-1.0;
  uv.x*=u_resolution.x/u_resolution.y;
  uv=mix(uv,abs(uv),u_key[2]);
  float g=max(u_good,0.0),lg=log(1.0+g);
  float t=u_time*(0.2+u_fader[0]*2.0);
  float s=2.0+u_knob[0]*10.0;
  float v=sin(uv.x*s+t)+sin(uv.y*(2.0+u_knob[1]*10.0)-t*1.3)+sin(length(uv)*s*0.7+t*0.7);
  v+=min(lg,2.0)*0.5*sin(uv.x*uv.y*s*2.0-t);
  vec3 c=0.5+0.5*sin(v*(1.0+u_fader[1]*3.0)+vec3(0.0,2.1,4.2));
  float steps=2.0+floor((1.0-u_fader[2])*30.0)+floor(lg*8.0);
  c=floor(c*steps)/steps;
  c*=1.0-u_key[4]*0.6*step(0.5,fract(gl_FragCoord.y*0.5));
  gl_FragColor=vec4(c,1.0);
}`},

];
