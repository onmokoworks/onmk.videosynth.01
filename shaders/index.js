// Shader list for the emulator (file:// pages cannot list or fetch files, so the sources live here).
// Each entry is a GLSL ES 1.00 fragment shader body: write main(); the host adds precision + uniforms
// (see AGENTS.md "Shader contract"). Keep the same text runnable on the Pi Zero.
//
// u_good (GOOD KNOB) grows without limit: 1.0 per full turn of the encoder, 0 after RESET.
// Never use it raw where it can blow up. Use it through bounded shapes: g01() saturates, fract()/sin() cycle,
// log() keeps adding detail slower and slower, so turning "always makes it a bit better" and never breaks.
window.SHADERS = [

{ name: 'TRUCHET', map: {"p_speed":{"src":"fader:0","inv":false},"p_roll":{"src":"fader:1","inv":false},"p_gap":{"src":"fader:2","inv":false},"p_width":{"src":"fader:3","inv":false},"p_bulge":{"src":"fader:4","inv":false}}, src: `
// メインの模様。背景 #fffaf0 に正方形のマスを敷き詰め、全部のマスを同じ向きの 1/4 円（左下の角と右上の角が中心）で埋める。
// 同じ向きに並べると、帯は左上から右下へ波打つ斜めの線になる。その斜めの帯を1本おきに #7fffd4 / #00bfff で塗り分ける。
// 弧は辺の真ん中から出て、となりの辺の真ん中へ抜ける。円より外へ膨らませて（スーパー楕円）、マスの真ん中でとなりの帯と
// 大きく重なる。重なる所では上の帯が下の帯を完全に隠し、どちらが上かはマスごとに入れ替わる（2色が交互に重なる編み目）。
// 帯を道路に見立てて、白っぽい玉 #f8f8ff が車のように帯に沿って左上から右下へ走る。下になった所では上の帯をくぐって隠れる。
// 帯ごとに速さが違い、間隔もまばら。玉の右下に薄い影が落ちる。画面全体はずっと左上から右下へ流れる。
// フェーダー：F0 全体の速さ（流れも玉も） / F1 玉の速さ / F2 玉の間隔 / F3 帯の太さ / F4 弧の膨らみ
// キー（押している間だけ効く。離すと0.2秒で戻る）：
//   K0 玉が大きくなる / K1 帯が太くなる / K2 2色が入れ替わる / K3 夜（背景が暗くなる）
//   K4 寄る（マスが大きくなる） / K5 影が遠くなる（浮き上がって見える） / K6 白黒 / K7 白く光る
uniform float p_speed;  // @param 0.0 3.0 1.0 全体の速さ（流れと玉の両方にかかる。0 で止まる）
uniform float p_scroll; // @param 0.0 1.0 0.2 流れる速さ（1秒に進むマス数）
uniform float p_roll;   // @param 0.0 2.0 0.6 玉の速さ（1秒に進む弧の数の平均）
uniform float p_gap;    // @param 1.5 8.0 3.0 玉どうしの間隔（弧の数）
uniform float p_width;  // @param 0.08 0.30 0.17 帯の太さ（半分の幅、マス単位）
uniform float p_bulge;  // @param 2.0 4.0 2.6 弧の膨らみ（2＝ふつうの円、大きいほど角ばってマスの真ん中に寄り、重なりが増える）

float hash(vec2 v){return fract(sin(dot(v,vec2(127.1,311.7)))*43758.5453);}
// 角からの「膨らんだ距離」（スーパー楕円の半径）。v は角から見た位置（0..1 の正の値）
float bulgeR(vec2 v){return pow(pow(v.x,p_bulge)+pow(v.y,p_bulge),1.0/p_bulge);}

// 片方の弧の上で、点 q（マスの中の位置）にいちばん近い玉までの距離。
// 帯は 左下の弧(x,y) → 右上の弧(x,y-1) → 左下の弧(x+1,y-1) → … と続くので、
// 帯に沿った位置 U は 左下の弧なら 2x＋進み、右上の弧なら 2x+1＋進み（進みは弧の中で 0→1）。
float carDist(vec2 q,vec2 cell,bool bl){
  float band,U,rad;
  if(bl){
    band=cell.x+cell.y;rad=bulgeR(q)-0.5;
    U=2.0*cell.x+clamp(1.0-atan(q.y,q.x)/1.5707963,0.0,1.0);            // 左の辺 → 下の辺
  }else{
    vec2 r=vec2(1.0)-q;band=cell.x+cell.y+1.0;rad=bulgeR(r)-0.5;
    U=2.0*cell.x+1.0+clamp(atan(r.y,r.x)/1.5707963,0.0,1.0);       // 上の辺 → 右の辺
  }
  float v=p_roll*(0.6+0.8*hash(vec2(band,3.1)));                  // 帯ごとの速さ
  float c=U-v*u_time*p_speed+hash(vec2(band,9.7))*p_gap;
  float k=floor(c/p_gap+0.5);                                     // いちばん近い玉の番号
  if(hash(vec2(k,band+0.37))<0.35) return 1e3;                    // ところどころ玉がいない
  return length(vec2((c-k*p_gap)*0.7853982,rad));                 // 弧1本の長さは π/4
}

// 模様そのもの。p はマス単位の座標、px は1ピクセルの大きさ
vec3 ground(vec2 p,float px){
  vec3 colA=vec3(0.498,1.0,0.831),colB=vec3(0.0,0.749,1.0),bg=vec3(1.0,0.980,0.941);
  vec3 ca=mix(colA,colB,u_key[2]),cb=mix(colB,colA,u_key[2]);colA=ca;colB=cb;   // K2 2色を入れ替える
  bg=mix(bg,vec3(0.06,0.07,0.12),u_key[3]);                                       // K3 夜
  float w=p_width+0.05*u_key[1],rb=0.07+0.06*u_key[0];                            // K1 帯を太く、K0 玉を大きく
  vec2 cell=floor(p),q=p-cell;
  float dBL=abs(bulgeR(q)-0.5);              // 左下の角が中心の弧（左の辺の真ん中 ↔ 下の辺の真ん中）
  float dTR=abs(bulgeR(vec2(1.0)-q)-0.5);    // 右上の角が中心の弧（上の辺の真ん中 ↔ 右の辺の真ん中）
  // 斜めの帯の番号：左下の弧は cell.x+cell.y、右上の弧はその次の帯。偶数と奇数で色を分ける
  bool even=mod(cell.x+cell.y,2.0)<0.5;
  vec3 cBL=even?colA:colB, cTR=even?colB:colA;
  // 上に来る弧：x が偶数のマスは左下の弧、奇数のマスは右上の弧。同じ2本の帯の重なりが交互に上下する
  bool blTop=mod(cell.x,2.0)<0.5;
  float dLo=blTop?dTR:dBL, dHi=blTop?dBL:dTR;
  vec3 cLo=blTop?cTR:cBL, cHi=blTop?cBL:cTR;
  float off=(2.5+9.0*u_key[5])*px*0.7071;                            // 影は画面の右下 45 度（K5 で遠くに）
  vec2 qs=q+vec2(-off,off);
  vec3 ball=vec3(0.973,0.973,1.0);
  vec3 c=bg;
  // 下の帯 → その上の玉 → 上の帯 → その上の玉、の順に重ねる
  c=mix(c,cLo,1.0-smoothstep(w-px,w+px,dLo));
  if(carDist(qs,cell,!blTop)<rb) c=mix(c,vec3(0.0),0.22);
  if(carDist(q,cell,!blTop)<rb) c=ball;
  c=mix(c,cHi,1.0-smoothstep(w-px,w+px,dHi));
  if(carDist(qs,cell,blTop)<rb) c=mix(c,vec3(0.0),0.22);
  if(carDist(q,cell,blTop)<rb) c=ball;
  return c;
}
void main(){
  float cells=5.0-2.0*u_key[4];                      // 画面の縦に並ぶマスの数（K4 で寄る）
  float px=cells/u_resolution.y;                     // 1ピクセルの大きさ（マス単位）
  vec2 p=gl_FragCoord.xy*px+u_time*p_speed*p_scroll*vec2(-1.0,1.0);   // 左上から右下へ流れる
  vec3 c=ground(p,px);
  c=mix(c,vec3(dot(c,vec3(0.299,0.587,0.114))),u_key[6]);  // K6 白黒
  c=mix(c,vec3(1.0),0.7*u_key[7]);                          // K7 白く光る
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
