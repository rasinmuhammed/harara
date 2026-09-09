import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { Planner } from "@/components/Planner";

export default function Page() {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main className="flex-1">
        <Planner />
      </main>
      <SiteFooter />
    </div>
  );
}
