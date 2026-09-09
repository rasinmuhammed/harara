import type { Metadata } from "next";
import { ChatApp } from "@/components/chat/ChatApp";

export const metadata: Metadata = {
  title: "Harara planner",
  description: "Describe a shift and read the work, ease off, or stop plan for the day.",
};

export default function AppPage() {
  return <ChatApp />;
}
