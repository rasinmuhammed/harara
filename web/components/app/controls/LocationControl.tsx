"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { Chip } from "@/components/ui/Chip";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/Popover";

const SiteMap = dynamic(() => import("@/components/map/SiteMap").then((m) => m.SiteMap), {
  ssr: false,
  loading: () => <div className="skeleton h-72 w-full rounded-lg" />,
});

type Loc = { lat: number; lon: number; name?: string };

export function LocationControl({
  value,
  label,
  onChange,
  flash,
}: {
  value: Loc;
  label: string;
  onChange: (v: Loc) => void;
  flash?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Chip label="Location" value={label} active={open} flash={flash} />
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,640px)] p-3">
        <SiteMap value={value} onChange={onChange} />
      </PopoverContent>
    </Popover>
  );
}
