import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";
import type { OrbState } from "@/store/agnesStore";

// State → (primary, accent) color pair. The orb is two-tone like the brand logo:
// a pearlescent inner highlight + a brand-tinted outer rim that shifts per state.
const STATE_PALETTE: Record<OrbState, { primary: string; accent: string; rim: string }> = {
  // Idle = the Spherecast logo itself: blue-pearl with lilac highlight, blue rim
  idle:      { primary: "#A0C3F7", accent: "#CFB3FE", rim: "#1F5FBE" },
  listening: { primary: "#1F5FBE", accent: "#1BA0EB", rim: "#1F5FBE" },
  thinking:  { primary: "#CFB3FE", accent: "#1BA0EB", rim: "#7B5FCC" },
  talking:   { primary: "#2BEFFC", accent: "#A0C3F7", rim: "#1BA0EB" },
  error:     { primary: "#ef4444", accent: "#fca5a5", rim: "#b91c1c" },
};
const STATE_COLORS: Record<OrbState, string> = {
  idle: "#1F5FBE",
  listening: "#1F5FBE",
  thinking: "#CFB3FE",
  talking: "#2BEFFC",
  error: "#ef4444",
};

// A high-segment icosphere with custom shader — wobbles + breathes + glows
// based on (state, level). All colors derived from state mapping above.
function OrbMesh({ state, level }: { state: OrbState; level: number }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uLevel: { value: 0 },
      uColor: { value: new THREE.Color(STATE_PALETTE.idle.primary) },
      uColor2: { value: new THREE.Color(STATE_PALETTE.idle.accent) },
      uRim: { value: new THREE.Color(STATE_PALETTE.idle.rim) },
      uIntensity: { value: 0.18 },
      uDistort: { value: 0.18 },
    }),
    [],
  );

  useFrame((_, dt) => {
    if (!matRef.current || !meshRef.current) return;
    const palette = STATE_PALETTE[state];
    const targetColor = new THREE.Color(palette.rim); // halo uses the rim color
    uniforms.uColor.value.lerp(new THREE.Color(palette.primary), Math.min(1, dt * 4));
    uniforms.uColor2.value.lerp(new THREE.Color(palette.accent), Math.min(1, dt * 4));
    uniforms.uRim.value.lerp(new THREE.Color(palette.rim), Math.min(1, dt * 4));

    // Smooth level
    const cur = uniforms.uLevel.value;
    uniforms.uLevel.value = cur + (level - cur) * Math.min(1, dt * 6);

    // Per-state targets
    let intensity = 0.16, distort = 0.18, rotSpeed = 0.05;
    if (state === "idle") { intensity = 0.16; distort = 0.18; rotSpeed = 0.05; }
    if (state === "listening") { intensity = 0.42 + level * 0.5; distort = 0.28 + level * 0.5; rotSpeed = 0.18; }
    if (state === "thinking") { intensity = 0.55; distort = 0.55; rotSpeed = 0.6; }
    if (state === "talking") { intensity = 0.5 + level * 0.6; distort = 0.32 + level * 0.7; rotSpeed = 0.2; }
    if (state === "error") { intensity = 0.4; distort = 0.2; rotSpeed = 0.1; }

    uniforms.uIntensity.value += (intensity - uniforms.uIntensity.value) * Math.min(1, dt * 4);
    uniforms.uDistort.value += (distort - uniforms.uDistort.value) * Math.min(1, dt * 4);

    uniforms.uTime.value += dt * (0.4 + rotSpeed);

    meshRef.current.rotation.y += dt * rotSpeed;
    meshRef.current.rotation.x += dt * rotSpeed * 0.4;

    // Breathing scale for idle, pulse-with-level otherwise
    const t = performance.now() / 1000;
    const breathe = 1 + Math.sin(t * 1.6) * 0.025;
    const reactive = 1 + uniforms.uLevel.value * 0.18;
    const targetScale = state === "idle" ? breathe : reactive;
    meshRef.current.scale.setScalar(meshRef.current.scale.x + (targetScale - meshRef.current.scale.x) * Math.min(1, dt * 6));

    if (haloRef.current) {
      const hs = 1.35 + uniforms.uLevel.value * 0.2 + (state === "thinking" ? 0.08 : 0);
      haloRef.current.scale.setScalar(haloRef.current.scale.x + (hs - haloRef.current.scale.x) * Math.min(1, dt * 5));
      const haloMat = haloRef.current.material as THREE.MeshBasicMaterial;
      haloMat.color.lerp(targetColor, Math.min(1, dt * 4));
      haloMat.opacity = 0.08 + uniforms.uIntensity.value * 0.18;
    }
  });

  return (
    <group>
      {/* Soft halo */}
      <mesh ref={haloRef}>
        <sphereGeometry args={[1.0, 32, 32]} />
        <meshBasicMaterial transparent opacity={0.12} color={STATE_COLORS[state]} depthWrite={false} />
      </mesh>

      {/* Main orb */}
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.95, 64]} />
        <shaderMaterial
          ref={matRef}
          uniforms={uniforms}
          transparent
          vertexShader={`
            uniform float uTime;
            uniform float uDistort;
            uniform float uLevel;
            varying vec3 vNormal;
            varying float vDistort;

            // Classic 3D simplex noise (Ashima)
            vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
            vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
            vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
            vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
            float snoise(vec3 v){
              const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
              vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
              vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
              vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
              i=mod289(i);
              vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
              float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
              vec4 j=p-49.0*floor(p*ns.z*ns.z);
              vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
              vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
              vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
              vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
              vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
              vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
              vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
              p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
              vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
              return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
            }

            void main(){
              vNormal = normal;
              float n = snoise(normal * 1.6 + vec3(uTime * 0.6));
              float n2 = snoise(normal * 3.4 + vec3(-uTime * 0.4, uTime * 0.3, uTime * 0.5));
              float d = (n * 0.6 + n2 * 0.4) * uDistort + uLevel * 0.18;
              vDistort = d;
              vec3 newPos = position + normal * d;
              gl_Position = projectionMatrix * modelViewMatrix * vec4(newPos, 1.0);
            }
          `}
          fragmentShader={`
            uniform vec3 uColor;   // primary (mid)
            uniform vec3 uColor2;  // accent (highlight)
            uniform vec3 uRim;     // rim
            uniform float uIntensity;
            uniform float uTime;
            varying vec3 vNormal;
            varying float vDistort;
            void main(){
              vec3 viewDir = vec3(0.0, 0.0, 1.0);
              float ndv = max(dot(normalize(vNormal), viewDir), 0.0);
              float fres = pow(1.0 - ndv, 2.2);
              // Pearlescent core: white highlight blends into primary, rim picks up brand tint
              vec3 pearl = vec3(1.0);
              vec3 inner = mix(pearl, uColor2, smoothstep(0.0, 0.7, ndv));
              vec3 mid   = mix(inner, uColor, 0.45 + vDistort * 0.4);
              vec3 col   = mix(mid, uRim, fres) + uRim * fres * uIntensity * 1.2;
              float alpha = 0.88 + fres * 0.12;
              gl_FragColor = vec4(col, alpha);
            }
          `}
        />
      </mesh>
    </group>
  );
}

interface VoiceOrbProps {
  state: OrbState;
  level: number;
  size?: number;
}

export function VoiceOrb({ state, level, size = 220 }: VoiceOrbProps) {
  return (
    <div
      className="relative"
      style={{ width: size, height: size }}
      aria-label={`Agnes voice orb — ${state}`}
      role="img"
    >
      {/* Outer soft glow ring driven by state */}
      <div
        className="absolute inset-0 rounded-full pointer-events-none transition-colors duration-500"
        style={{
          background: `radial-gradient(circle at 50% 50%, ${STATE_COLORS[state]}33 0%, transparent 65%)`,
          filter: "blur(18px)",
          transform: `scale(${1 + level * 0.18})`,
        }}
      />
      <Canvas
        camera={{ position: [0, 0, 2.6], fov: 45 }}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        dpr={[1, 2]}
        style={{ background: "transparent" }}
      >
        <ambientLight intensity={0.6} />
        <pointLight position={[2, 3, 4]} intensity={0.8} />
        <Suspense fallback={null}>
          <OrbMesh state={state} level={level} />
        </Suspense>
      </Canvas>
    </div>
  );
}
