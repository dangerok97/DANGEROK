/**
 * Lightweight rich text for /ora-ai harness — Quiet Premium, no new deps.
 * Supports paragraphs, headings, lists, bold/italic, inline code, simple math.
 */
import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

type Props = {
  text: string;
  color: string;
  secondaryColor?: string;
};

type Block =
  | { type: 'h'; level: number; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] };

function preprocess(raw: string): string {
  let t = raw || '';
  // Strip fenced code markers if model leaked them
  t = t.replace(/```(?:json|markdown|md)?/gi, '').replace(/```/g, '');
  // Display math → readable plain
  t = t.replace(/\$\$([\s\S]*?)\$\$/g, (_, m) => m.trim());
  t = t.replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => m.trim());
  t = t.replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => m.trim());
  t = t.replace(/\$([^$\n]+)\$/g, (_, m) => m.trim());
  // Common LaTeX tokens
  t = t
    .replace(/\\pm/g, '±')
    .replace(/\\times/g, '×')
    .replace(/\\cdot/g, '·')
    .replace(/\\leq/g, '≤')
    .replace(/\\geq/g, '≥')
    .replace(/\\neq/g, '≠')
    .replace(/\\approx/g, '≈')
    .replace(/\\infty/g, '∞')
    .replace(/\\rightarrow/g, '→')
    .replace(/\\to/g, '→')
    .replace(/\\alpha/g, 'α')
    .replace(/\\beta/g, 'β')
    .replace(/\\gamma/g, 'γ')
    .replace(/\\pi/g, 'π')
    .replace(/\\sum/g, '∑')
    .replace(/\\int/g, '∫')
    .replace(/\\sqrt\{([^}]+)\}/g, '√($1)')
    .replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '($1)/($2)')
    .replace(/\\mathbf\{([^}]+)\}/g, '$1')
    .replace(/\\mathrm\{([^}]+)\}/g, '$1')
    .replace(/\\text\{([^}]+)\}/g, '$1')
    .replace(/\\left|\\right/g, '')
    .replace(/[{}]/g, '');
  return t;
}

function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const h = /^(#{1,3})\s+(.+)$/.exec(line);
    if (h) {
      blocks.push({ type: 'h', level: h[1].length, text: h[2].trim() });
      i += 1;
      continue;
    }
    if (/^\s*[-*•]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*•]\s+/, '').trim());
        i += 1;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, '').trim());
        i += 1;
      }
      blocks.push({ type: 'ol', items });
      continue;
    }
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const parts: string[] = [line.trim()];
    i += 1;
    while (i < lines.length && lines[i].trim() && !/^(#{1,3})\s+/.test(lines[i]) && !/^\s*[-*•]\s+/.test(lines[i]) && !/^\s*\d+[.)]\s+/.test(lines[i])) {
      parts.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: 'p', text: parts.join(' ') });
  }
  return blocks;
}

function Inline({ text, color }: { text: string; color: string }) {
  // Split **bold**, *italic*, `code`
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) {
      nodes.push(<Text key={key++}>{text.slice(last, m.index)}</Text>);
    }
    const tok = m[0];
    if (tok.startsWith('**')) {
      nodes.push(
        <Text key={key++} style={styles.bold}>
          {tok.slice(2, -2)}
        </Text>,
      );
    } else if (tok.startsWith('*')) {
      nodes.push(
        <Text key={key++} style={styles.italic}>
          {tok.slice(1, -1)}
        </Text>,
      );
    } else {
      nodes.push(
        <Text key={key++} style={styles.code}>
          {tok.slice(1, -1)}
        </Text>,
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(<Text key={key++}>{text.slice(last)}</Text>);
  return <Text style={[styles.body, { color }]}>{nodes}</Text>;
}

export function RichOraText({ text, color, secondaryColor }: Props) {
  const blocks = useMemo(() => parseBlocks(preprocess(text)), [text]);
  if (!text?.trim()) return null;
  return (
    <View style={styles.wrap}>
      {blocks.map((b, idx) => {
        if (b.type === 'h') {
          return (
            <Text
              key={idx}
              style={[
                styles.body,
                b.level === 1 ? styles.h1 : b.level === 2 ? styles.h2 : styles.h3,
                { color },
              ]}
            >
              {b.text}
            </Text>
          );
        }
        if (b.type === 'ul' || b.type === 'ol') {
          return (
            <View key={idx} style={styles.list}>
              {b.items.map((it, j) => (
                <View key={j} style={styles.li}>
                  <Text style={{ color: secondaryColor || color, marginRight: 8 }}>
                    {b.type === 'ol' ? `${j + 1}.` : '•'}
                  </Text>
                  <View style={styles.liBody}>
                    <Inline text={it} color={color} />
                  </View>
                </View>
              ))}
            </View>
          );
        }
        return (
          <View key={idx} style={styles.p}>
            <Inline text={b.text} color={color} />
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  p: {},
  body: { fontSize: 16, lineHeight: 24 },
  h1: { fontSize: 20, fontWeight: '700', lineHeight: 28, marginTop: 4 },
  h2: { fontSize: 18, fontWeight: '600', lineHeight: 26, marginTop: 4 },
  h3: { fontSize: 16, fontWeight: '600', lineHeight: 24, marginTop: 2 },
  bold: { fontWeight: '700' },
  italic: { fontStyle: 'italic' },
  code: {
    fontSize: 14,
  },
  list: { gap: 4 },
  li: { flexDirection: 'row', alignItems: 'flex-start' },
  liBody: { flex: 1 },
});
