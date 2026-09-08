"""
The optional agent layer: typed deterministic tools, a model-agnostic LLM
interface, and the parse / brief / monitor components built on top.

Nothing in this package computes a heat metric, a schedule or a threshold.
Those come from src.wbgt, src.scheduler and src.heat_stress through the
tools in src.agent.tools. See docs/llm_layer_plan.md.
"""
