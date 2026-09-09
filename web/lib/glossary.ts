// One plain sentence per term. No jargon inside the explanation.
export const GLOSSARY: Record<string, string> = {
  WBGT:
    "A single temperature that combines heat, humidity, sun, and wind into one number for how hard it is for the body to cool itself.",
  "wet-bulb globe temperature":
    "A single temperature that combines heat, humidity, sun, and wind into one number for how hard it is for the body to cool itself.",
  acclimatised:
    "Used to the heat. The body adapts over one to two weeks, sweating sooner and cooling better. A crew that arrived recently is not yet adapted.",
  "work fraction":
    "The share of an hour spent working rather than resting in shade. 1.0 is the full hour, 0.5 is thirty minutes.",
  "retained load":
    "Heat that builds up in the body across the day and bleeds off slowly during rest. The plan keeps the peak of this as low as it can.",
  "p90 tail":
    "The level the retained load reaches on the worst tenth of the day. A lower tail means fewer bad stretches, not just a lower average.",
  "forecast lead":
    "How far ahead the forecast is. A plan for tomorrow uses a one-day-ahead forecast, which is more accurate than one for next week.",
  "stop-work line":
    "Qatar Decision 17/2021 requires outdoor work to stop when WBGT reaches 32.1 C, on top of the fixed midday ban.",
};

export const GLOSSARY_TERMS = Object.keys(GLOSSARY);
