import { Fragment, type ReactNode } from "react";

// Renders the small Markdown subset the coach writes — paragraphs,
// "-"/"*"/"1." lists, and **bold** — as React elements. Deliberately no
// HTML injection: the reply is model output, so it's rendered as text.

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <Fragment key={i}>{part}</Fragment>,
  );
}

const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

// Groups consecutive list lines so "Here's the plan:\n- a\n- b" renders as a
// paragraph followed by a list, even without a blank line between them.
function groups(block: string): { list: boolean; lines: string[] }[] {
  const out: { list: boolean; lines: string[] }[] = [];
  for (const line of block.split("\n")) {
    if (!line.trim()) continue;
    const list = BULLET.test(line);
    const last = out[out.length - 1];
    if (last && last.list === list) last.lines.push(line);
    else out.push({ list, lines: [line] });
  }
  return out;
}

export default function CoachText({ text }: { text: string }) {
  return (
    <div className="coach-text">
      {text.trim().split(/\n{2,}/).flatMap((block, i) =>
        groups(block).map((group, g) => {
          const key = `${i}-${g}`;
          if (group.list) {
            const items = group.lines.map((line, j) => <li key={j}>{inline(line.replace(BULLET, ""))}</li>);
            return /^\s*\d/.test(group.lines[0]) ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
          }
          return (
            <p key={key}>
              {group.lines.map((line, j) => (
                <Fragment key={j}>
                  {j > 0 && <br />}
                  {inline(line.replace(/^#{1,4}\s+/, ""))}
                </Fragment>
              ))}
            </p>
          );
        }),
      )}
    </div>
  );
}
