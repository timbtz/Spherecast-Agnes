/**
 * Agnes Orb — WebGL 3D sphere visual component.
 * Manually created as ElevenLabs CLI requires Node 20+.
 * Uses React Three Fiber with animated sphere and color-based state feedback.
 */
import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { AgentState } from '@/types/agnes'

interface OrbProps {
  colors?: [string, string]
  agentState?: AgentState
  seed?: number
  inputVolumeRef?: React.RefObject<number>
  outputVolumeRef?: React.RefObject<number>
  className?: string
}

function Sphere({ colors, agentState, inputVolumeRef, outputVolumeRef, seed = 42 }: OrbProps) {
  const meshRef = useRef<THREE.Mesh>(null!)
  const materialRef = useRef<THREE.ShaderMaterial>(null!)

  const [c1, c2] = useMemo(() => {
    const parseColor = (hex: string) => new THREE.Color(hex)
    return [parseColor(colors?.[0] ?? '#CADCFC'), parseColor(colors?.[1] ?? '#A0B9D1')]
  }, [colors])

  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uColor1: { value: c1 },
    uColor2: { value: c2 },
    uVolume: { value: 0 },
    uSeed: { value: seed },
    uState: { value: 0 },
  }), [])

  uniforms.uColor1.value = c1
  uniforms.uColor2.value = c2

  const vertexShader = `
    uniform float uTime;
    uniform float uVolume;
    uniform float uSeed;
    uniform float uState;
    varying vec3 vNormal;
    varying vec3 vPosition;

    float noise(vec3 p) {
      return sin(p.x * 2.1 + uSeed * 0.1) * cos(p.y * 1.7) * sin(p.z * 2.3 + uTime * 0.5);
    }

    void main() {
      vNormal = normal;
      float speed = uState == 1.0 ? 2.5 : uState == 2.0 ? 4.0 : uState == 3.0 ? 3.0 : 1.0;
      float amp = 0.08 + uVolume * 0.3 + (uState == 2.0 ? 0.06 : 0.0);
      vec3 pos = position;
      pos += normal * noise(position + uTime * speed * 0.3) * amp;
      vPosition = pos;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }
  `

  const fragmentShader = `
    uniform vec3 uColor1;
    uniform vec3 uColor2;
    varying vec3 vNormal;
    varying vec3 vPosition;

    void main() {
      float t = clamp(vPosition.y * 0.5 + 0.5, 0.0, 1.0);
      vec3 color = mix(uColor2, uColor1, t);
      float rim = 1.0 - max(dot(vNormal, vec3(0.0, 0.0, 1.0)), 0.0);
      color = mix(color, vec3(1.0), rim * 0.15);
      gl_FragColor = vec4(color, 1.0);
    }
  `

  useFrame((state) => {
    if (!materialRef.current) return
    materialRef.current.uniforms.uTime.value = state.clock.elapsedTime
    const vol = agentState === 'listening'
      ? (inputVolumeRef?.current ?? 0)
      : agentState === 'talking'
        ? (outputVolumeRef?.current ?? 0)
        : 0
    materialRef.current.uniforms.uVolume.value = vol
    materialRef.current.uniforms.uState.value =
      agentState === 'listening' ? 1 :
      agentState === 'thinking' ? 2 :
      agentState === 'talking' ? 3 : 0
    if (meshRef.current) {
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.1
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.07) * 0.1
    }
  })

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 8]} />
      <shaderMaterial
        ref={materialRef}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
      />
    </mesh>
  )
}

export function Orb({ colors, agentState, seed, inputVolumeRef, outputVolumeRef, className }: OrbProps) {
  return (
    <div className={`w-full h-full ${className ?? ''}`}>
      <Canvas camera={{ position: [0, 0, 2.5], fov: 45 }} gl={{ antialias: true, alpha: true }}>
        <ambientLight intensity={0.5} />
        <pointLight position={[2, 2, 2]} intensity={1} />
        <Sphere
          colors={colors}
          agentState={agentState}
          seed={seed}
          inputVolumeRef={inputVolumeRef}
          outputVolumeRef={outputVolumeRef}
        />
      </Canvas>
    </div>
  )
}
