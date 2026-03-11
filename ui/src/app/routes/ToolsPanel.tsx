import type { ToolItem } from "../../lib/types";

type ToolsPanelProps = {
  tools: ToolItem[];
};

export function ToolsPanel({ tools }: ToolsPanelProps) {
  return (
    <section className="panel">
      <h2>Tools</h2>
      <ul className="tools-list">
        {tools.map((tool) => (
          <li key={tool.name}>
            <strong>{tool.name}</strong>
            <p>{tool.description}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
