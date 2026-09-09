import { getDohaPlan } from "@/lib/day";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";
import { SmoothScroll } from "@/components/landing/SmoothScroll";
import { Hero } from "@/components/landing/Hero";
import { Problem } from "@/components/landing/Problem";
import { Idea } from "@/components/landing/Idea";
import { Replay } from "@/components/landing/Replay";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Evidence } from "@/components/landing/Evidence";
import { Close } from "@/components/landing/Close";
import { ContourDivider } from "@/components/visual/ContourDivider";

export default async function Page() {
  const plan = await getDohaPlan();
  return (
    <>
      <SmoothScroll />
      <Nav />
      <main id="main">
        <Hero plan={plan} />
        <ContourDivider className="mx-auto max-w-content px-5 pt-10" />
        <Problem />
        <Idea plan={plan} />
        <ContourDivider className="mx-auto max-w-content px-5 pt-6" />
        <Replay />
        <HowItWorks />
        <Evidence />
        <ContourDivider className="mx-auto max-w-content px-5 pt-6" />
        <Close />
      </main>
      <Footer />
    </>
  );
}
