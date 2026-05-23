import React, { forwardRef } from 'react';

type MotionTarget = Record<string, unknown>;

export type MotionProps = {
  initial?: MotionTarget | boolean;
  animate?: MotionTarget | boolean;
  exit?: MotionTarget | boolean;
  transition?: unknown;
  variants?: unknown;
  whileHover?: MotionTarget;
  whileTap?: MotionTarget;
  whileInView?: MotionTarget;
  viewport?: unknown;
  layout?: unknown;
  drag?: unknown;
  dragConstraints?: unknown;
  dragElastic?: unknown;
  dragMomentum?: unknown;
};

type MotionComponent = React.ComponentType<MotionProps & Record<string, unknown>>;

type AnimatePresenceProps = {
  children?: React.ReactNode;
  initial?: boolean;
  mode?: string;
};

const motionComponentCache = new Map<string, MotionComponent>();

function isMotionTarget(value: unknown): value is MotionTarget {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function pickMotionValue(value: unknown): string | number | undefined {
  const candidate = Array.isArray(value) ? value[value.length - 1] : value;
  return typeof candidate === 'string' || typeof candidate === 'number'
    ? candidate
    : undefined;
}

function toLength(value: string | number): string | number {
  return typeof value === 'number' ? `${value}px` : value;
}

function toDegree(value: string | number): string {
  return typeof value === 'number' ? `${value}deg` : value;
}

function motionTargetToStyle(target: unknown, baseStyle?: React.CSSProperties): React.CSSProperties {
  if (!isMotionTarget(target)) {
    return baseStyle ?? {};
  }

  const nextStyle: React.CSSProperties = { ...(baseStyle ?? {}) };
  const transforms: string[] = [];

  for (const [key, rawValue] of Object.entries(target)) {
    const value = pickMotionValue(rawValue);
    if (value === undefined) continue;

    if (key === 'x') {
      transforms.push(`translateX(${toLength(value)})`);
      continue;
    }
    if (key === 'y') {
      transforms.push(`translateY(${toLength(value)})`);
      continue;
    }
    if (key === 'scale') {
      transforms.push(`scale(${value})`);
      continue;
    }
    if (key === 'rotate') {
      transforms.push(`rotate(${toDegree(value)})`);
      continue;
    }

    (nextStyle as Record<string, string | number>)[key] = value;
  }

  if (transforms.length > 0) {
    nextStyle.transform = [baseStyle?.transform, ...transforms].filter(Boolean).join(' ');
  }

  return nextStyle;
}

function createMotionComponent(tagName: string): MotionComponent {
  const MotionElement = forwardRef<HTMLElement, MotionProps & Record<string, unknown>>(
    (
      {
        initial: _initial,
        animate,
        exit: _exit,
        transition: _transition,
        variants: _variants,
        whileHover: _whileHover,
        whileTap: _whileTap,
        whileInView: _whileInView,
        viewport: _viewport,
        layout: _layout,
        drag: _drag,
        dragConstraints: _dragConstraints,
        dragElastic: _dragElastic,
        dragMomentum: _dragMomentum,
        style,
        ...rest
      },
      ref
    ) => {
      const mergedStyle = motionTargetToStyle(animate, style as React.CSSProperties | undefined);
      return React.createElement(tagName, { ...rest, ref, style: mergedStyle });
    }
  );

  MotionElement.displayName = `MotionStub(${tagName})`;
  return MotionElement as MotionComponent;
}

export const motion = new Proxy(
  {},
  {
    get(_target, tagName: string) {
      if (!motionComponentCache.has(tagName)) {
        motionComponentCache.set(tagName, createMotionComponent(tagName));
      }
      return motionComponentCache.get(tagName);
    },
  }
) as Record<string, MotionComponent> & {
  div: MotionComponent;
  h3: MotionComponent;
  p: MotionComponent;
  button: MotionComponent;
};

export function AnimatePresence({ children }: AnimatePresenceProps) {
  return <>{children}</>;
}
