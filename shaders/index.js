// Shader list for the emulator (file:// pages cannot list or fetch files, so the sources live here).
// Each entry is a GLSL ES 1.00 fragment shader body: write main(); the host adds precision + uniforms
// (see AGENTS.md "Shader contract"). Keep the same text runnable on the Pi Zero.
//
// u_good (GOOD KNOB) grows without limit: 1.0 per full turn of the encoder, 0 after RESET.
// Never use it raw where it can blow up. Use it through bounded shapes: g01() saturates, fract()/sin() cycle,
// log() keeps adding detail slower and slower, so turning "always makes it a bit better" and never breaks.
window.SHADERS = [

{ name: 'TRUCHET', src: `
// メインの模様（つまみの割り当てはあとで）。背景 #fffaf0 に正方形のマスを敷き詰め、各マスに 1/4 円の弧を2組重ねる。
// 「右上↔左下」の弧（#7fffd4 の層）と「左上↔右下」の弧（#00bfff の層）。どちらが上かはマスごとに互い違い（市松）で、
// 2色の線が編み物のように上下に交差する。白っぽい玉 #f8f8ff が線の上を転がり、右下に薄い影が落ちる。
// ・画面全体がずっと左上から右下へ流れる。
// ・回る単位の正方形は、模様のマスから半マスずらしてある（マスの角＝円の中心に正方形の中心がくる）。
//   ときどきランダムに1つの正方形が浮き上がり、画面の面内で（z 軸まわりに）90 度回って着地する。
//   回った分はそのまま残るので、時間とともに正方形ごとに向きがばらけていく。
uniform float p_scroll; // @param 0.0 1.0 0.2 流れる速さ（1秒に進むマス数）
uniform float p_every;  // @param 5.0 120.0 30.0 1つの正方形が回る平均の間隔（秒）。小さいほど、ばらけるのが早い
uniform float p_flip;   // @param 0.6 3.0 1.4 1回（90 度）回るのにかける時間（秒）
uniform float p_roll;   // @param 0.0 2.0 0.5 玉の速さ（1秒に進む弧の数）

float hash(vec2 v){return fract(sin(dot(v,vec2(127.1,311.7)))*43758.5453);}
float smoother(float f){return f*f*f*(f*(f*6.0-15.0)+10.0);}
mat2 rot(float a){return mat2(cos(a),-sin(a),sin(a),cos(a));}

// 編み物の模様そのもの（回す前の世界）。p はマス単位の座標、px は1ピクセルの大きさ
vec3 ground(vec2 p,float px){
  vec3 colA=vec3(0.498,1.0,0.831),colB=vec3(0.0,0.749,1.0),bg=vec3(1.0,0.980,0.941);
  float w=0.08,rb=0.055;
  vec2 cell=floor(p),q=p-cell,qm=vec2(1.0-q.x,q.y);
  float dA=min(abs(length(q-vec2(1.0))-0.5),abs(length(q)-0.5));     // 右上↔左下の弧
  float dB=min(abs(length(qm-vec2(1.0))-0.5),abs(length(qm)-0.5));   // 左上↔右下の弧
  bool topA=mod(cell.x+cell.y,2.0)<0.5;                               // このマスで上になる層
  float dTop=topA?dA:dB,dBot=topA?dB:dA;
  vec3 c=bg;
  c=mix(c,topA?colB:colA,1.0-smoothstep(w-px,w+px,dBot));             // 下の層
  c=mix(c,bg,1.0-smoothstep(w+1.5*px,w+2.5*px,dTop));                 // 上の層のまわりのすき間（重なりが読めるように）
  c=mix(c,topA?colA:colB,1.0-smoothstep(w-px,w+px,dTop));             // 上の層
  // 玉：上の層の2本の弧の上を転がる（影は画面の右下 45 度に 2.5 ピクセル）
  float s=fract(u_time*p_roll),t1=3.1415927+s*1.5707963,t2=1.5707963-s*1.5707963;
  vec2 B1=vec2(1.0)+0.5*vec2(cos(t1),sin(t1)),B2=0.5*vec2(cos(t2),sin(t2));
  vec2 qq=topA?q:qm;
  float off=2.5*px*0.7071;
  vec2 qs=qq+(topA?vec2(-off,off):vec2(off,off));
  if(min(length(qs-B1),length(qs-B2))<rb) c=vec3(0.78);
  if(min(length(qq-B1),length(qq-B2))<rb) c=vec3(0.973,0.973,1.0);
  return c;
}
// 回る正方形の予定表（正方形ごとにランダムな間隔とずれ）。x = いまの回転の進み 0..1（回っていなければ 1）、
// y = 着地済みの回数（向き＝y×90 度）
vec2 schedule(vec2 sq){
  float I=p_every*(0.6+0.8*hash(sq+1.3));
  float tt=u_time-(2.0+hash(sq+7.1)*p_every*1.5);    // 最初に回る時刻までは全部そろったまま
  if(tt<0.0) return vec2(1.0,0.0);
  float n=floor(tt/I),f=(tt-n*I)/p_flip;
  return f<1.0?vec2(f,n):vec2(1.0,n+1.0);
}
void main(){
  float cells=5.0;                                   // 画面の縦に並ぶマスの数
  float px=cells/u_resolution.y;                     // 1ピクセルの大きさ（マス単位）
  vec2 p=gl_FragCoord.xy*px+u_time*p_scroll*vec2(-1.0,1.0);   // 左上から右下へ流れる
  vec3 shadowC=vec3(0.78);
  // 回る正方形は半マスずらした格子：正方形 sq は [sq+0.5, sq+1.5]、中心は sq+1（マスの角）
  vec2 sq0=floor(p-0.5);
  // ---- 地面：自分の正方形（浮いていなければ、着地済みの向きで描く） ----
  vec2 sc=schedule(sq0),ctr=sq0+1.0;
  vec3 c;
  if(sc.x<1.0) c=vec3(0.86,0.84,0.80);               // 浮き上がった正方形の抜けた跡
  else c=ground(ctr+rot(-sc.y*1.5707963)*(p-ctr),px);
  // ---- 浮き上がって回る正方形（周り9つから探して、一番手前を描く） ----
  float best=0.0;
  for(int n=0;n<9;n++){
    vec2 sq=sq0+vec2(float(n-n/3*3)-1.0,float(n/3)-1.0);
    vec2 k=schedule(sq);
    if(k.x>=1.0) continue;
    float e=smoother(k.x),lift=sin(3.1415927*e);
    float S=1.0+0.3*lift;                            // 浮いた分だけ大きく見せる
    float ang=(k.y+e)*1.5707963;                     // 着地済みの向きから、さらに 90 度へ
    vec2 cen=sq+1.0,rel=p-cen;
    vec2 ls=rot(-ang)*(rel-vec2(1.0,-1.0)*0.15*lift)/S;   // 影（浮いた高さに合わせて右下へ）
    if(max(abs(ls.x),abs(ls.y))<0.5&&S>best) c=mix(c,shadowC,0.7);
    vec2 l=rot(-ang)*rel/S;
    if(max(abs(l.x),abs(l.y))>0.5||S<=best) continue;
    best=S;
    c=ground(cen+l,px);                              // 正方形の中身＝模様を回したもの
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
