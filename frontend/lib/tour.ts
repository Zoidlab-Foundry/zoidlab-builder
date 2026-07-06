// Instructional mode — step definitions. Add a step = add an entry.
// `target` is a CSS selector for the element to spotlight (omit for a centered card).
export interface TourStep {
  target?: string;
  title: string;
  body: string;
  placement?: "top" | "bottom" | "left" | "right" | "center";
}

export const TOUR_STEPS: TourStep[] = [
  {
    title: "Welcome to the Workflow Builder",
    body: "Build AI workflows visually — drag components onto the canvas, connect them, test, and deploy. Here's a 30-second tour.",
    placement: "center",
  },
  {
    target: '[data-tour="library"]',
    title: "1 · Node Library",
    body: "Every building block lives here — AI models, prompts, logic, and integrations. Drag any node onto the canvas to add it.",
    placement: "right",
  },
  {
    target: '[data-tour="canvas"]',
    title: "2 · The Canvas",
    body: "Drop nodes here and wire them up by dragging from one node's handle to another. Pan, zoom, and use the minimap to navigate.",
    placement: "left",
  },
  {
    target: '[data-tour="canvas"]',
    title: "3 · Right-click for actions",
    body: "Right-click a node, an edge, or empty space for built-in controls — configure, duplicate, add nodes, auto-arrange, and more. No browser menu.",
    placement: "left",
  },
  {
    target: '[data-tour="copilot"]',
    title: "4 · AI Copilot",
    body: "Short on time? Describe a workflow in plain English and Copilot builds the whole graph for you to refine.",
    placement: "bottom",
  },
  {
    target: '[data-tour="config"]',
    title: "5 · Configure nodes",
    body: "Select any node to set it up here — pick a model, write prompts, set conditions. Everything's configurable without code.",
    placement: "left",
  },
  {
    target: '[data-tour="run"]',
    title: "6 · Run & watch it live",
    body: "Hit Run to execute. Nodes light up in real time — yellow running, green complete, red failed — with output and token counts.",
    placement: "bottom",
  },
  {
    target: '[data-tour="guide"]',
    title: "You're ready",
    body: "That's the tour. Replay it anytime from Guide. Now go build something.",
    placement: "bottom",
  },
];
