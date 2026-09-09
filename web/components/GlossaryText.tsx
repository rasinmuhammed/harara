"use client";
import { Fragment } from "react";
import { GLOSSARY_TERMS } from "@/lib/glossary";
import { Term } from "./Term";

const RE = new RegExp(
  `\\b(${GLOSSARY_TERMS.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`,
  "gi",
);
const KEY_BY_LOWER: Record<string, string> = Object.fromEntries(
  GLOSSARY_TERMS.map((t) => [t.toLowerCase(), t]),
);

/** Render plain text, wrapping the first occurrence of each glossary term. */
export function GlossaryText({ text }: { text: string }) {
  const used = new Set<string>();
  const parts = text.split(RE);
  return (
    <>
      {parts.map((p, i) => {
        const key = KEY_BY_LOWER[p.toLowerCase()];
        if (key && !used.has(key)) {
          used.add(key);
          return (
            <Term key={i} k={key}>
              {p}
            </Term>
          );
        }
        return <Fragment key={i}>{p}</Fragment>;
      })}
    </>
  );
}
