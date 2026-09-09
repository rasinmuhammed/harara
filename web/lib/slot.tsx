"use client";

import { cloneElement, forwardRef, isValidElement } from "react";
import { cn } from "./cn";

/**
 * Minimal Radix-style Slot: merge this component's props (notably className and
 * ref) onto its single child, so <Button asChild><Link/></Button> renders one
 * element. Enough for our needs; not a full implementation.
 */
export const Slot = forwardRef<any, { children?: React.ReactNode } & Record<string, any>>(
  function Slot({ children, className, ...rest }, ref) {
    if (!isValidElement(children)) return null;
    const child = children as React.ReactElement<any>;
    return cloneElement(child, {
      ...rest,
      ...child.props,
      ref,
      className: cn(className, child.props.className),
    });
  },
);
