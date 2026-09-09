import type { WorkloadClass } from "./types";

// Plain labels and real examples, from the activity descriptions in
// src/heat_stress.py. Categories unchanged, only how they are shown.
export const WORKLOADS: { value: WorkloadClass; label: string; hint: string }[] = [
  {
    value: "light",
    label: "Light",
    hint: "standing, light hand or arm work, for example inspection or light assembly",
  },
  {
    value: "moderate",
    label: "Moderate",
    hint: "steady hand and leg work and walking, for example carrying light loads or plastering",
  },
  {
    value: "heavy",
    label: "Heavy",
    hint: "hard sustained effort, for example digging, shovelling, carrying heavy loads, pouring concrete",
  },
  {
    value: "very_heavy",
    label: "Very heavy",
    hint: "near maximal effort, for example breaking ground by hand or climbing stairs with a load",
  },
];

export const ACCLIM_LABEL = "Has the crew been working in this heat for more than two weeks";
export const ACCLIM_HINT =
  "A body that is not used to the heat is at higher risk at the same conditions.";
