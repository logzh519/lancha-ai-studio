<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvasRef = ref<HTMLCanvasElement | null>(null)
let frame = 0
let cleanup: (() => void) | null = null

onMounted(() => {
  const canvas = canvasRef.value
  const context = canvas?.getContext('2d')
  if (!canvas || !context) return

  const pointer = { x: -9999, y: -9999, active: false }
  const particles: Array<{ x: number; y: number; vx: number; vy: number; size: number; tone: number; hover: number }> = []
  const palette = ['#2f7fff', '#19c7b7', '#80b4ff']
  let width = 0
  let height = 0

  function resize(): void {
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    width = canvas!.clientWidth
    height = canvas!.clientHeight
    canvas!.width = Math.round(width * ratio)
    canvas!.height = Math.round(height * ratio)
    context!.setTransform(ratio, 0, 0, ratio, 0, 0)
    particles.length = 0
    const count = Math.min(170, Math.max(90, Math.round((width * height) / 10500)))
    for (let index = 0; index < count; index += 1) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.42,
        vy: (Math.random() - 0.5) * 0.42,
        size: 1.5 + Math.random() * 2.1,
        tone: index % palette.length,
        hover: 0,
      })
    }
  }

  function onPointerMove(event: PointerEvent): void {
    const bounds = canvas!.getBoundingClientRect()
    pointer.x = event.clientX - bounds.left
    pointer.y = event.clientY - bounds.top
    pointer.active = pointer.x >= 0 && pointer.x <= width && pointer.y >= 0 && pointer.y <= height
  }

  function onPointerLeave(): void {
    pointer.active = false
  }

  function draw(): void {
    context!.clearRect(0, 0, width, height)

    for (const particle of particles) {
      const dx = particle.x - pointer.x
      const dy = particle.y - pointer.y
      const distance = Math.hypot(dx, dy) || 1
      const influence = pointer.active ? Math.max(0, 1 - distance / 230) : 0
      if (influence > 0) {
        particle.vx += (dx / distance) * influence * 0.18
        particle.vy += (dy / distance) * influence * 0.18
      }
      particle.hover += (influence - particle.hover) * 0.16
      particle.vx *= 0.992
      particle.vy *= 0.992
      particle.x += particle.vx
      particle.y += particle.vy
      if (particle.x < -12) particle.x = width + 12
      if (particle.x > width + 12) particle.x = -12
      if (particle.y < -12) particle.y = height + 12
      if (particle.y > height + 12) particle.y = -12
    }

    for (let first = 0; first < particles.length; first += 1) {
      for (let second = first + 1; second < particles.length; second += 1) {
        const a = particles[first]
        const b = particles[second]
        const distance = Math.hypot(a.x - b.x, a.y - b.y)
        if (distance > 146) continue
        const alpha = (1 - distance / 146) * (0.2 + Math.max(a.hover, b.hover) * 0.42)
        context!.beginPath()
        context!.moveTo(a.x, a.y)
        context!.lineTo(b.x, b.y)
        context!.strokeStyle = `rgba(72, 142, 255, ${alpha})`
        context!.lineWidth = 0.9 + Math.max(a.hover, b.hover) * 0.6
        context!.stroke()
      }
    }

    for (const particle of particles) {
      context!.beginPath()
      context!.arc(particle.x, particle.y, particle.size + particle.hover * 2.7, 0, Math.PI * 2)
      context!.fillStyle = particle.hover > 0.32 ? '#d6e6ff' : palette[particle.tone]
      context!.globalAlpha = 0.54 + particle.hover * 0.46
      context!.fill()
    }
    context!.globalAlpha = 1
    frame = window.requestAnimationFrame(draw)
  }

  resize()
  draw()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerleave', onPointerLeave)
  cleanup = () => {
    window.cancelAnimationFrame(frame)
    window.removeEventListener('resize', resize)
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerleave', onPointerLeave)
  }
})

onBeforeUnmount(() => cleanup?.())
</script>

<template>
  <canvas ref="canvasRef" class="particle-field" aria-hidden="true" />
</template>

<style scoped>
.particle-field {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
</style>
