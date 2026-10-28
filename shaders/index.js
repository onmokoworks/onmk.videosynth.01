// Shader list for the emulator (file:// pages cannot list or fetch files, so the sources live here).
// Each entry is a GLSL ES 1.00 fragment shader body: write main(); the host adds precision + uniforms
// (see AGENTS.md "Shader contract"). Keep the same text runnable on the Pi Zero.
//
// u_good (GOOD KNOB) grows without limit: 1.0 per full turn of the encoder, 0 after RESET.
// Never use it raw where it can blow up. Use it through bounded shapes: g01() saturates, fract()/sin() cycle,
// log() keeps adding detail slower and slower, so turning "always makes it a bit better" and never breaks.
window.SHADERS = [

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
