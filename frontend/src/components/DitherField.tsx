import { useEffect, useRef } from "react";

// 8x8 Bayer matrix, normalized to thresholds in [0, 1).
const BAYER = [
  0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28,
  52, 20, 62, 30, 54, 22, 3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7,
  39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21,
].map((n) => n / 64);

interface DitherFieldProps {
  /** 0 = nearly empty, 1 = dense. Changing it doesn't restart the animation. */
  intensity: number;
  /** CSS pixels per dither cell. */
  cell?: number;
  /** Horizontal position (0-1) where the field starts; it fades in over the next 30%. */
  fadeFrom?: number;
  className?: string;
}

/** An animated ordered-dither field, drawn in the current text color. */
export function DitherField({
  intensity,
  cell = 3,
  fadeFrom = 0,
  className = "",
}: DitherFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const intensityRef = useRef(intensity);

  useEffect(() => {
    intensityRef.current = intensity;
  }, [intensity]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");

    if (!canvas || !context) {
      return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frameId = 0;

    const draw = (time: number) => {
      const width = Math.max(1, Math.ceil(canvas.clientWidth / cell));
      const height = Math.max(1, Math.ceil(canvas.clientHeight / cell));

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      const image = context.createImageData(width, height);
      const level = intensityRef.current;
      const t = time * 0.00035;

      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          const nx = x / width;
          const ny = y / height;
          const wave = Math.sin(nx * 6.0 + t * 1.3) * Math.cos(ny * 5.0 - t) * 0.5 + 0.5;
          const blobX = 0.65 + Math.sin(t * 0.7) * 0.15;
          const blobY = 0.45 + Math.cos(t * 0.5) * 0.2;
          const distance = Math.hypot(nx - blobX, (ny - blobY) * 1.4);
          const blob = Math.max(0, 1 - distance * 1.8);
          const fade = Math.max(0, Math.min(1, (nx - fadeFrom) / 0.3, (1 - ny) * 2.5, ny * 4));
          const value = (wave * 0.45 + blob * 0.75) * level * fade;
          const threshold = BAYER[(y % 8) * 8 + (x % 8)] ?? 1;
          const offset = (y * width + x) * 4;

          image.data[offset + 3] = value > threshold + 0.03 ? 255 : 0;
        }
      }

      // Draw the dot pattern as a mask, then fill it with the CSS text color.
      // The canvas parses any CSS color (Tailwind v4 uses oklch), including opacity.
      context.putImageData(image, 0, 0);
      context.globalCompositeOperation = "source-in";
      context.fillStyle = getComputedStyle(canvas).color;
      context.fillRect(0, 0, width, height);
      context.globalCompositeOperation = "source-over";

      if (!reduceMotion) {
        frameId = requestAnimationFrame(draw);
      }
    };

    frameId = requestAnimationFrame(draw);

    return () => cancelAnimationFrame(frameId);
  }, [cell, fadeFrom]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`[image-rendering:pixelated] ${className}`}
    />
  );
}
