import { getDohaPlan } from "@/lib/day";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";
import { SmoothScroll } from "@/components/landing/SmoothScroll";
import { Hero } from "@/components/landing/Hero";
import { Problem } from "@/components/landing/Problem";
import { Idea } from "@/components/landing/Idea";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Evidence } from "@/components/landing/Evidence";
import { Close } from "@/components/landing/Close";

export default async function Page() {
  const plan = await getDohaPlan();
  return (
    <>
      <SmoothScroll />
      <Nav />
      <main id="main">
        <Hero plan={plan} />
        <Problem />
        <Idea plan={plan} />
        <HowItWorks />
        <Evidence />
        <Close />
      </main>
      <Footer />
    </>
  );
}
