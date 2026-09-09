import type { Metadata } from "next";
import { AppShell } from "@/components/app/AppShell";

export const metadata: Metadata = {
  title: "Harara planner",
  description:
    "Set the site, the work, the day and the hours. Get a work / ease off / stop plan for the shift, with every number traceable to its source.",
};

export default function AppPage() {
  return <AppShell />;
}
