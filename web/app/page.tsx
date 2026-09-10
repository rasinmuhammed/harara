import { getDohaPlan } from "@/lib/day";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";
import { SmoothScroll } from "@/components/landing/SmoothScroll";
import { Hero } from "@/components/landing/Hero";
import { Problem } from "@/components/landing/Problem";
import { Findings } from "@/components/landing/Findings";
import { Method } from "@/components/landing/Method";
import { LanguageLayer } from "@/components/landing/LanguageLayer";
import { Idea } from "@/components/landing/Idea";
import { Replay } from "@/components/landing/Replay";
import { UseCases } from "@/components/landing/UseCases";
import { Close } from "@/components/landing/Close";
import { ContourDivider } from "@/components/visual/ContourDivider";
import { Warm } from "@/components/Warm";

export default async function Page() {
  const plan = await getDohaPlan();
  return (
    <>
      <Warm />
      <SmoothScroll />
      <Nav />
      <main id="main">
        <Hero plan={plan} />
        <ContourDivider className="mx-auto max-w-content px-5 pt-10" />
        <Problem />
        <Findings />
        <Method />
        <LanguageLayer />
        <Idea plan={plan} />
        <ContourDivider className="mx-auto max-w-content px-5 pt-6" />
        <Replay />
        <UseCases />
        <ContourDivider className="mx-auto max-w-content px-5 pt-6" />
        <Close />
      </main>
      <Footer />
    </>
  );
}
