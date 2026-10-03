/** Word-level diff for rendering red/green highlights in the internal dashboard.
 * Plain LCS over whitespace-split tokens -- good enough for article-length text;
 * no external dep needed for this one build-time computation. */
export type DiffPart = { text: string; tag: "same" | "del" | "ins" };

function tokenize(s: string): string[] {
  return s.match(/\s+|\S+/g) ?? [];
}

export function diffWords(before: string, after: string): { before: DiffPart[]; after: DiffPart[] } {
  const a = tokenize(before);
  const b = tokenize(after);
  const n = a.length, m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    const row = dp[i]!, next = dp[i + 1]!;
    for (let j = m - 1; j >= 0; j--) {
      row[j] = a[i] === b[j] ? next[j + 1]! + 1 : Math.max(next[j]!, row[j + 1]!);
    }
  }
  const beforeParts: DiffPart[] = [];
  const afterParts: DiffPart[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    const ai = a[i]!, bj = b[j]!;
    if (ai === bj) {
      beforeParts.push({ text: ai, tag: "same" });
      afterParts.push({ text: bj, tag: "same" });
      i++; j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      beforeParts.push({ text: ai, tag: "del" });
      i++;
    } else {
      afterParts.push({ text: bj, tag: "ins" });
      j++;
    }
  }
  while (i < n) { beforeParts.push({ text: a[i]!, tag: "del" }); i++; }
  while (j < m) { afterParts.push({ text: b[j]!, tag: "ins" }); j++; }
  return { before: beforeParts, after: afterParts };
}
