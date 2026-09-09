"use client";
import { useEffect, useRef, useState } from "react";

export function Reveal({
  children,
  delay = 0,
  as: Tag = "div",
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  as?: any;
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const [shown, setShown] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const el = ref.current;
    if (!el) return;
    // already on screen at mount -> show now
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight * 1.1) {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    // safety: never leave content hidden
    const t = setTimeout(() => setShown(true), 1500);
    return () => {
      io.disconnect();
      clearTimeout(t);
    };
  }, []);

  return (
    <Tag
      ref={ref}
      className={className}
      style={
        mounted
          ? {
              opacity: shown ? 1 : 0,
              transform: shown ? "none" : "translateY(12px)",
              transition: `opacity .5s var(--ease) ${delay}ms, transform .5s var(--ease) ${delay}ms`,
            }
          : undefined
      }
    >
      {children}
    </Tag>
  );
}
